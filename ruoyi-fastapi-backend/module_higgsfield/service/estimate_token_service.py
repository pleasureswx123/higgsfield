"""短时估价确认令牌，只携带作用域与摘要，不携带价格正文或秘密。"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
from datetime import datetime

from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService

MAX_TTL_SECONDS = 3600
MAX_TOKEN_LENGTH = 4096


class EstimateTokenService:
    def __init__(self, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) < hashlib.sha256().digest_size:
            raise ValueError('估价签名密钥必须至少32字节')
        self._key = key

    @classmethod
    def from_environment(cls) -> 'EstimateTokenService':
        try:
            raw = os.environ['HF_ESTIMATE_TOKEN_KEY']
            return cls(base64.b64decode(raw, validate=True))
        except (KeyError, ValueError, binascii.Error) as error:
            raise ValueError('未配置有效的估价签名密钥') from error

    @staticmethod
    def _encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')

    @staticmethod
    def _timestamp(now: datetime) -> int:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('估价时点必须包含时区')
        return int(now.timestamp())

    @staticmethod
    def request_hash(payload: GenerationInput) -> str:
        return WriteService.digest(payload.model_dump(by_alias=True, exclude={'estimate_token'}))

    @staticmethod
    def price_hash(prices: dict, estimate: dict) -> str:
        # 读取时点本身不构成价格变化；区间修订、分项及预估策略变化均要求重新确认。
        stable = {
            purpose: {key: value for key, value in price.items() if key != 'selectedAt'}
            for purpose, price in prices.items()
        }
        return WriteService.digest({'prices': stable, 'estimate': estimate})

    def _signature(self, body: str) -> str:
        return self._encode(
            hmac.new(self._key, b'higgsfield:estimate:v1:' + body.encode('ascii'), hashlib.sha256).digest()
        )

    def issue(
        self,
        *,
        actor_id: int,
        payload: GenerationInput,
        prices: dict,
        estimate: dict,
        now: datetime,
        ttl_seconds: int = 300,
    ) -> str:
        if (
            type(ttl_seconds) is not int
            or not 0 < ttl_seconds <= MAX_TTL_SECONDS
            or type(actor_id) is not int
            or actor_id <= 0
        ):
            raise ValueError('估价作用域或有效期无效')
        issued = self._timestamp(now)
        claims = {
            'v': 1,
            'actor': str(actor_id),
            'project': payload.project_id,
            'request': self.request_hash(payload),
            'price': self.price_hash(prices, estimate),
            'iat': issued,
            'exp': issued + ttl_seconds,
        }
        body = self._encode(json.dumps(claims, sort_keys=True, separators=(',', ':')).encode())
        return body + '.' + self._signature(body)

    def verify(
        self, token: str, *, actor_id: int, payload: GenerationInput, prices: dict, estimate: dict, now: datetime
    ) -> None:
        current = self._timestamp(now)
        try:
            if (
                not isinstance(token, str)
                or len(token) > MAX_TOKEN_LENGTH
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token)
            ):
                raise ValueError('令牌格式无效')
            body, signature = token.split('.')
            if not hmac.compare_digest(signature, self._signature(body)):
                raise ValueError('签名无效')
            raw = base64.urlsafe_b64decode(body + '=' * (-len(body) % 4))
            claims = json.loads(raw)
            if (
                not isinstance(claims, dict)
                or claims.get('v') != 1
                or claims.get('actor') != str(actor_id)
                or claims.get('project') != payload.project_id
                or claims.get('request') != self.request_hash(payload)
                or type(claims.get('iat')) is not int
                or type(claims.get('exp')) is not int
                or not 0 < claims['exp'] - claims['iat'] <= MAX_TTL_SECONDS
                or current < claims['iat']
            ):
                raise ValueError('作用域或有效期无效')
        except (ValueError, TypeError, binascii.Error):
            # 仅返回统一错误，不泄露令牌中的用户、项目或价格摘要。
            WorkspaceService.conflict('ESTIMATE_TOKEN_INVALID', '估价确认令牌无效，请重新预估')
        if current >= claims['exp']:
            WorkspaceService.conflict('ESTIMATE_EXPIRED', '估价已过期，请重新预估')
        if claims.get('price') != self.price_hash(prices, estimate):
            WorkspaceService.conflict('PRICE_CHANGED', '价格或预估策略已变化，请重新预估并确认')

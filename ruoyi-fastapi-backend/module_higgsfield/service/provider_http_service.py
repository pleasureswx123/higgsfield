"""受控供应商HTTP传输：固定端点、不跟随重定向、不自动重试生成。"""

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Self
from urllib.parse import quote

import httpx
from pydantic import SecretStr, TypeAdapter

from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion
from module_higgsfield.entity.vo.provider_submission_vo import SafeIdentifier
from module_higgsfield.entity.vo.provider_vo import ConnectionFields
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.provider_upload_stream import ProviderUploadStream
from module_higgsfield.service.videoplus_response_service import unique_object

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
HARD_RESPONSE_BYTES = 256 * 1024 * 1024
STREAM_CHUNK_BYTES = 65536
MIN_SECRET_LENGTH, MAX_SECRET_LENGTH = 8, 4096
ASCII_FIRST, ASCII_LAST = 33, 126


def invalid_constant(value: str) -> None:
    raise ValueError('响应JSON包含非有限数字')


@dataclass(frozen=True)
class ProviderHttpResult:
    transport: Literal['response', 'timeout', 'network_error']
    http_status: int | None = None
    body: object = field(default=None, repr=False)
    issue: str | None = None


class ProviderHttpService:
    def __init__(
        self, connection: ConnectionFields, secret: SecretStr, *, max_response_bytes: int = MAX_RESPONSE_BYTES
    ) -> None:
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= HARD_RESPONSE_BYTES:
            raise ValueError('响应大小限制无效')
        value = secret.get_secret_value()
        if not MIN_SECRET_LENGTH <= len(value) <= MAX_SECRET_LENGTH or any(
            ord(char) < ASCII_FIRST or ord(char) > ASCII_LAST for char in value
        ):
            raise ValueError('供应商密钥格式无效')
        # 复制后重新校验，调用方不能在初始化后修改主机白名单。
        self.connection = ConnectionFields.model_validate(connection.model_dump())
        self.secret = secret
        self.max_response_bytes = max_response_bytes

    @classmethod
    def from_versions(
        cls,
        connection_version: HfProviderConnectionVersion,
        credential_version: HfCredentialVersion,
        *,
        crypto: CredentialCryptoService | None = None,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ) -> Self:
        """调用方先完成原任务绑定校验，再在短会话结束后使用此传输对象。"""
        if credential_version.connection_version_id != connection_version.connection_version_id:
            raise ValueError('凭据与连接配置版本不匹配')
        secret = (
            (crypto or CredentialCryptoService())
            .decrypt(
                credential_version,
                credential_version.credential_id,
                credential_version.connection_version_id,
                credential_version.version_no,
            )
            .decode('ascii')
        )
        connection = ConnectionFields(
            name='固定供应商连接',
            baseUrl=connection_version.base_url,
            adapterVersion=connection_version.adapter_version,
            config=connection_version.config,
        )
        return cls(connection, SecretStr(secret), max_response_bytes=max_response_bytes)

    async def submit(self, payload: dict) -> ProviderHttpResult:
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        return await self._request('POST', 'v1/chat/completions', content)

    async def poll(self, task_id: str) -> ProviderHttpResult:
        identity = TypeAdapter(SafeIdentifier).validate_python(task_id)
        return await self._request('GET', 'v1/video/tasks/' + quote(identity, safe=''), None)

    async def upload(self, upload: ProviderUploadStream) -> ProviderHttpResult:
        try:
            return await self._request(
                'POST',
                'v1/assets/upload',
                upload.chunks(),
                content_type=upload.content_type,
                content_length=upload.content_length,
            )
        except (ValueError, OSError):
            return ProviderHttpResult('network_error', issue='UPLOAD_SOURCE_CHANGED_OR_UNREADABLE')

    async def _request(
        self,
        method: str,
        path: str,
        content: bytes | AsyncIterator[bytes] | None,
        *,
        content_type: str = 'application/json',
        content_length: int | None = None,
    ) -> ProviderHttpResult:
        config = self.connection.config
        timeout = httpx.Timeout(
            config.read_timeout_seconds,
            connect=config.connect_timeout_seconds,
            write=config.operation_timeout_seconds,
            pool=config.connect_timeout_seconds,
        )
        headers = {
            'Authorization': 'Bearer ' + self.secret.get_secret_value(),
            'X-Biz-Id': config.biz_id,
            'Content-Type': content_type,
            'Accept': 'application/json',
            'Accept-Encoding': 'identity',
        }
        if content_length is not None:
            headers['Content-Length'] = str(content_length)
        try:
            async with (
                asyncio.timeout(config.operation_timeout_seconds),
                httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client,
                client.stream(method, self.connection.base_url + path, headers=headers, content=content) as response,
            ):
                if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                    return ProviderHttpResult('response', response.status_code, issue='RESPONSE_ENCODING_UNSUPPORTED')
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=STREAM_CHUNK_BYTES):
                    if len(data) + len(chunk) > self.max_response_bytes:
                        return ProviderHttpResult('response', response.status_code, issue='RESPONSE_TOO_LARGE')
                    data.extend(chunk)
                try:
                    body = json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)
                except (ValueError, UnicodeError, RecursionError):
                    return ProviderHttpResult('response', response.status_code, issue='RESPONSE_JSON_INVALID')
                return ProviderHttpResult('response', response.status_code, body)
        except (TimeoutError, httpx.TimeoutException):
            return ProviderHttpResult('timeout')
        except httpx.RequestError:
            # 错误对象可能包含URL或请求，禁止写入业务返回或日志。
            return ProviderHttpResult('network_error')

"""受控供应商HTTP传输：固定端点、不跟随重定向、不自动重试生成。"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Self
from urllib.parse import quote, urlsplit

import httpx
from pydantic import SecretStr, TypeAdapter

from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion
from module_higgsfield.entity.vo.provider_submission_vo import SafeIdentifier
from module_higgsfield.entity.vo.provider_vo import ConnectionFields
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.provider_decode_service import ProviderDecodeService
from module_higgsfield.service.provider_upload_stream import ProviderUploadStream
from module_higgsfield.service.videoplus_response_service import unique_object
from utils.output_source_util import validate_output_source
from module_higgsfield.service.provider_network_diagnostic import error_chain, response_facts

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
    diagnostic_body: str | None = field(default=None, repr=False)
    diagnostic: dict | None = None


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
        self.evidence_writer = None
        self.network_trace = None
        self.secret = secret
        self.max_response_bytes = max_response_bytes

    def configure_sync_image_timeout(self) -> None:
        """同步图片包含模型等待和正文下载，独立限时且不改变持久连接版本。"""
        config = self.connection.config
        total = min(900, config.task_timeout_seconds)
        values = config.model_dump()
        values.update(operation_timeout_seconds=total,
                      read_timeout_seconds=min(300, total),
                      connect_timeout_seconds=min(config.connect_timeout_seconds, total))
        self.connection.config = type(config).model_validate(values)

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

    async def register_asset(self, url: str, *, project: str, asset_type: str, name: str = '') -> ProviderHttpResult:
        """注册已上传的素材；不重试注册，也不将临时签名地址写入普通日志。"""
        validate_output_source(url)
        if project not in {'eva', 'nova'} or asset_type not in {'Image', 'Video', 'Audio'}:
            raise ValueError('素材库项目或素材类型无效')
        payload = {'URL': url, 'AssetType': asset_type, 'ProjectName': project}
        if name:
            payload['Name'] = name
        return await self._request('POST', 'v1/mm/assets', json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    async def get_asset(self, asset_id: str) -> ProviderHttpResult:
        """查询原素材状态；生成时仍使用 asset:// 引用，不替换为签名下载地址。"""
        if not isinstance(asset_id, str) or not re.fullmatch(r'asset-[A-Za-z0-9_-]{1,128}', asset_id):
            raise ValueError('供应商素材编号无效')
        return await self._request('POST', 'v1/mm/assets/get', json.dumps({'Id': asset_id}).encode('utf-8'))

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
        from module_higgsfield.service.provider_exchange_service import ProviderExchangeService
        return await ProviderExchangeService.capture(
            self, method, path, content, content_type,
            lambda: self._send(method, path, content, content_type=content_type, content_length=content_length),
        )

    async def _send(
        self, method, path, content, *, content_type='application/json', content_length=None,
    ) -> ProviderHttpResult:
        from module_higgsfield.service.provider_connection_pool import request_transport, local_bindings
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
        http_status = None
        response = None
        phase = 'request'
        received_bytes = 0
        facts = {'connectTimeoutSeconds': config.connect_timeout_seconds,
                 'readTimeoutSeconds': config.read_timeout_seconds,
                 'operationTimeoutSeconds': config.operation_timeout_seconds,
                 'trustEnvironmentProxy': False, 'followRedirects': False,
                 'automaticRetries': 0, 'httpxVersion': httpx.__version__}
        facts['outboundLocalAddress'] = local_bindings().get(urlsplit(self.connection.base_url).hostname)
        try:
            async with (
                asyncio.timeout(config.operation_timeout_seconds),
                httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False, transport=request_transport()) as client,
                client.stream(method, self.connection.base_url + path, headers=headers, content=content,
                    extensions={"trace": self.network_trace} if self.network_trace else {}) as response,
            ):
                http_status = response.status_code
                facts.update(response_facts(response))
                phase = 'response_body'
                data = bytearray()
                try:
                    decoder = ProviderDecodeService(response.headers.get('content-encoding', 'identity'), self.max_response_bytes)
                    async for chunk in response.aiter_raw(chunk_size=STREAM_CHUNK_BYTES):
                        received_bytes += len(chunk)
                        data.extend(decoder.feed(chunk))
                    decoder.finish()
                except ValueError:
                    return ProviderHttpResult('response', response.status_code, issue='RESPONSE_ENCODING_INVALID_OR_TOO_LARGE',
                                              diagnostic={**facts, 'phase': 'response_body', 'receivedBytes': received_bytes})
                try:
                    body = json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid_constant)
                except (ValueError, UnicodeError, RecursionError):
                    return ProviderHttpResult(
                        'response', response.status_code, issue='RESPONSE_JSON_INVALID',
                        diagnostic_body=bytes(data[:32000]).decode('utf-8', errors='replace')
                        + ('[超长正文已截断]' if len(data) > 32000 else ''),
                        diagnostic={**facts, 'phase': 'response_decode', 'receivedBytes': received_bytes},
                    )
                if isinstance(body, dict):
                    # 仅保留调用编号和成本证据，不保存密钥额度、余额等其他响应头。
                    headers_fact = {}
                    cost = response.headers.get('x-litellm-response-cost', '')
                    call_id = response.headers.get('x-litellm-call-id', '')
                    if re.fullmatch(r'[0-9]{1,14}(\.[0-9]{1,20})?', cost):
                        headers_fact['responseCost'] = cost
                    if re.fullmatch(r'[A-Za-z0-9_-]{1,128}', call_id):
                        headers_fact['callId'] = call_id
                    body['_platformGatewayHeaders'] = headers_fact
                return ProviderHttpResult('response', response.status_code, body,
                                          diagnostic={**facts, 'phase': 'complete', 'receivedBytes': received_bytes})
        except (TimeoutError, httpx.RequestError) as error:
            # 仅保存结构化异常类别，异常正文可能携带密钥、签名地址或请求内容。
            causes = error_chain(error)
            timed_out = isinstance(error, (TimeoutError, httpx.TimeoutException))
            if response is not None:
                received_bytes = response.num_bytes_downloaded
            return ProviderHttpResult(
                'timeout' if timed_out else 'network_error', http_status,
                issue='RESPONSE_BODY_INTERRUPTED' if http_status is not None else 'REQUEST_TRANSPORT_FAILED',
                diagnostic={**facts, 'phase': phase, 'exceptionType': type(error).__name__,
                            'causeTypes': [cause['type'] for cause in causes],
                            'errorChain': causes, 'receivedBytes': received_bytes},
            )

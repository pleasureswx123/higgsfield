"""固定DNS地址的有界媒体下载；不发送供应商Key、不跟随重定向。"""

import asyncio
import hashlib
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from module_higgsfield.service.storage_io_service import open_source
from module_higgsfield.service.storage_service import StorageService

CHUNK_BYTES = 65536
HTTPS_PORT = 443
MAX_TIMEOUT_SECONDS, ASCII_FIRST, HTTP_OK = 3600, 33, 200


@dataclass(frozen=True)
class OutputDownloadPolicy:
    allowed_hosts: tuple[str, ...]
    max_bytes: int
    timeout_seconds: int = 120
    allowed_ports: tuple[int, ...] = (HTTPS_PORT,)
    local_test: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_hosts or type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError('必须配置下载允许主机和字节上限')
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError('下载总时限无效')


class OutputDownloadService:
    def __init__(self, storage: StorageService, policy: OutputDownloadPolicy) -> None:
        if policy.local_test and (
            storage.policy.mode != 'local-test' or os.getenv('APP_ENV', 'dev') not in {'dev', 'test', 'local'}
        ):
            raise ValueError('回环下载只允许本地测试存储和开发环境')
        self.storage, self.policy = storage, policy

    async def target(self, source_url: str) -> tuple[httpx.URL, str, str]:
        parsed = urlsplit(source_url)
        if (
            parsed.hostname not in self.policy.allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.fragment
            or any(ord(char) < ASCII_FIRST for char in source_url)
            or parsed.scheme not in ({'http', 'https'} if self.policy.local_test else {'https'})
        ):
            raise ValueError('媒体下载源不符合主机和协议白名单')
        port = parsed.port or (HTTPS_PORT if parsed.scheme == 'https' else 80)
        if port not in self.policy.allowed_ports:
            raise ValueError('媒体下载端口未授权')
        addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        ips = {ipaddress.ip_address(item[4][0]) for item in addresses}
        if not ips or any(not (ip.is_global or (self.policy.local_test and ip.is_loopback)) for ip in ips):
            raise ValueError('媒体下载DNS解析到了未授权网络')
        # 连接到已经检查的IP，保留Host及TLS主机名校验，防止第二次DNS解析换到内网。
        address = sorted(ips, key=lambda ip: (ip.version, str(ip)))[0]
        target = httpx.URL(source_url).copy_with(host=str(address))
        host = parsed.hostname + (f':{port}' if parsed.port else '')
        return target, host, parsed.hostname

    async def _download(self, source_url: str, *, kind: str, key: str, created: list[str]) -> dict:
        if kind not in {'image', 'video'}:
            raise ValueError('只允许归档图片和视频')
        async with asyncio.timeout(self.policy.timeout_seconds):
            target, host, tls_name = await self.target(source_url)
            digest, size = hashlib.sha256(), 0
            # 直接使用传输对象，避免客户端INFO日志打印带签名的请求URL。
            async with httpx.AsyncHTTPTransport(retries=0, trust_env=False) as transport:
                request = httpx.Request(
                    'GET',
                    target,
                    headers={'Host': host, 'Accept-Encoding': 'identity'},
                    extensions={
                        'sni_hostname': tls_name,
                        'timeout': {'connect': 10, 'read': 30, 'write': 30, 'pool': 10},
                    },
                )
                response = await transport.handle_async_request(request)
                try:
                    if (
                        response.status_code != HTTP_OK
                        or response.headers.get('content-encoding', 'identity').lower() != 'identity'
                    ):
                        raise ValueError('媒体下载响应状态或编码不可用')
                    async with open_source(self.storage, key, write=True) as handle:
                        created.append(key)
                        async for chunk in response.aiter_bytes(chunk_size=CHUNK_BYTES):
                            size += len(chunk)
                            if size > min(self.policy.max_bytes, self.storage.policy.max_bytes):
                                raise ValueError('媒体下载超过允许大小')
                            digest.update(chunk)
                            await asyncio.to_thread(handle.write, chunk)
                        await asyncio.to_thread(handle.flush)
                        await asyncio.to_thread(os.fsync, handle.fileno())
                        metadata = await asyncio.to_thread(self.storage.verify_media, handle)
                        if not metadata['mime_type'].startswith(kind + '/'):
                            raise ValueError('下载媒体实际类型与输出类型不一致')
                finally:
                    await response.aclose()
            return {'storage_key': key, 'sha256': digest.hexdigest(), 'byte_size': size, **metadata}

    async def download(self, source_url: str, *, kind: str) -> dict:
        key = 'media/' + uuid4().hex
        created = []
        try:
            return await self._download(source_url, kind=kind, key=key, created=created)
        except BaseException:
            try:
                if created:
                    await asyncio.to_thread(self.storage.remove_unbound_key, key)
            except Exception:
                # NAS不可用时保留未绑定文件待清理，不将清理错误冒充下载根因。
                pass
            raise

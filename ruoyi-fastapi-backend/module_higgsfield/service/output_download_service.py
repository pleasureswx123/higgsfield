"""固定DNS地址的有界媒体下载；不发送供应商Key、不跟随重定向。"""

import asyncio
import hashlib
import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4
from time import perf_counter

import httpx

from module_higgsfield.service.storage_io_service import open_source
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.output_range_download import download_ranges, range_facts, strong_etag

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
    range_concurrency: int = 4

    def __post_init__(self) -> None:
        if not self.allowed_hosts or type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError('必须配置下载允许主机和字节上限')
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError('下载总时限无效')
        if type(self.range_concurrency) is not int or not 1 <= self.range_concurrency <= 4:
            raise ValueError('分段下载并发必须为1至4')


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

    async def _download(self, source_url: str, *, kind: str, key: str, created: list[str], progress=None) -> dict:
        if kind not in {'image', 'video'}:
            raise ValueError('只允许归档图片和视频')
        started, last_report = perf_counter(), 0.0
        metrics = {'requests': 0, 'resumeCount': 0, 'receivedBytes': 0, 'connections': 1,
                   'dnsSeconds': None, 'firstByteSeconds': None}
        async def report(size, total, stage='downloading', force=False):
            nonlocal last_report
            now = perf_counter()
            if progress is not None and (force or now - last_report >= 5):
                last_report = now
                await progress({**metrics, 'bytes': size, 'totalBytes': total,
                                'elapsedSeconds': round(now - started, 3), 'stage': stage})

        async with asyncio.timeout(self.policy.timeout_seconds):
            await report(0, None, force=True)
            target, host, tls_name = await self.target(source_url)
            metrics['dnsSeconds'] = round(perf_counter() - started, 3)
            size, total = 0, None
            maximum = min(self.policy.max_bytes, self.storage.policy.max_bytes)
            # 直接使用传输对象，避免客户端INFO日志打印带签名的请求URL。
            async with httpx.AsyncHTTPTransport(retries=0, trust_env=False) as transport:
                def request(headers=None):
                    return httpx.Request('GET', target,
                        headers={'Host': host, 'Accept-Encoding': 'identity', **(headers or {})},
                        extensions={'sni_hostname': tls_name,
                                    'timeout': {'connect': 10, 'read': 30, 'write': 30, 'pool': 10}})
                probe = kind == 'video' and self.policy.range_concurrency > 1
                metrics['requests'] += 1
                response = await transport.handle_async_request(request({'Range': 'bytes=0-0'} if probe else None))
                metrics['firstByteSeconds'] = round(perf_counter() - started, 3)
                try:
                    ranged = False
                    if probe and response.status_code == 206:
                        begin, end, total = range_facts(response)
                        if (begin, end) != (0, 0) or total > maximum:
                            raise ValueError('媒体下载范围或大小无效')
                        etag = strong_etag(response)
                        ranged = etag is not None and total >= 1_048_576
                        await response.aclose()
                        if not ranged:
                            metrics['requests'] += 1
                            response = await transport.handle_async_request(request())
                    if (
                        (not ranged and response.status_code != HTTP_OK)
                        or response.headers.get('content-encoding', 'identity').lower() != 'identity'
                    ):
                        raise ValueError('媒体下载响应状态或编码不可用')
                    if not ranged:
                        length = response.headers.get('content-length')
                        total = int(length) if length is not None else None
                        if total is not None and not 0 < total <= maximum:
                            raise ValueError('媒体下载超过允许大小')
                    async with open_source(self.storage, key, write=True) as handle:
                        created.append(key)
                        await report(0, total, force=True)
                        if ranged:
                            metrics['connections'] = self.policy.range_concurrency
                            await download_ranges(transport, request, handle, total, etag,
                                                  self.policy.range_concurrency, report, metrics)
                            size = total
                        else:
                            async for chunk in response.aiter_bytes(chunk_size=CHUNK_BYTES):
                                size += len(chunk)
                                if size > maximum:
                                    raise ValueError('媒体下载超过允许大小')
                                await asyncio.to_thread(handle.write, chunk)
                                metrics['receivedBytes'] += len(chunk)
                                await report(size, total)
                            if total is not None and size != total:
                                raise ValueError('下载文件长度不完整')
                        await asyncio.to_thread(handle.flush)
                        await asyncio.to_thread(os.fsync, handle.fileno())
                        await report(size, total, 'verifying', True)
                        def checksum():
                            handle.seek(0)
                            digest = hashlib.sha256()
                            while chunk := handle.read(CHUNK_BYTES):
                                digest.update(chunk)
                            return digest.hexdigest()
                        digest = await asyncio.to_thread(checksum)
                        metadata = await asyncio.to_thread(self.storage.verify_media, handle)
                        if not metadata['mime_type'].startswith(kind + '/'):
                            raise ValueError('下载媒体实际类型与输出类型不一致')
                        await report(size, total, 'complete', True)
                finally:
                    await response.aclose()
            return {'storage_key': key, 'sha256': digest, 'byte_size': size, **metadata}

    async def download(self, source_url: str, *, kind: str, progress=None) -> dict:
        key = 'media/' + uuid4().hex
        created = []
        latest, started = {}, perf_counter()
        async def record(value):
            latest.update(value)
            if progress is not None:
                await progress(value)
        try:
            return await self._download(source_url, kind=kind, key=key, created=created, progress=record)
        except BaseException as error:
            if latest and progress is not None and isinstance(error, Exception):
                code = ('timeout' if isinstance(error, TimeoutError) else
                        'network' if isinstance(error, httpx.TransportError) else
                        'invalid_response' if isinstance(error, ValueError) else 'storage_or_state')
                try:
                    await progress({**latest, 'stage': 'failed', 'errorCode': code,
                                    'elapsedSeconds': round(perf_counter() - started, 3)})
                except Exception:
                    pass  # 记录失败不能覆盖原始异常，旧租约也不能继续写回。
            try:
                if created:
                    await asyncio.to_thread(self.storage.remove_unbound_key, key)
            except Exception:
                # NAS不可用时保留未绑定文件待清理，不将清理错误冒充下载根因。
                pass
            raise

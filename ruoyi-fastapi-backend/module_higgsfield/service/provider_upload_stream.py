"""有界读取已授权文件句柄，按固定大小与摘要输出multipart请求。"""

import asyncio
import hashlib
import re
from collections.abc import AsyncIterator
from typing import BinaryIO
from uuid import uuid4

CHUNK_BYTES = 65536


class ProviderUploadStream:
    def __init__(
        self,
        source: BinaryIO,
        *,
        file_name: str,
        mime_type: str,
        byte_size: int,
        sha256: str,
        max_bytes: int,
    ) -> None:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', file_name):
            raise ValueError('外部上传文件名须使用安全ASCII名称')
        if not re.fullmatch(r'(image|video)/[a-z0-9.+-]+', mime_type):
            raise ValueError('上传接口只开放图片和视频MIME')
        if type(max_bytes) is not int or type(byte_size) is not int or not 0 < byte_size <= max_bytes:
            raise ValueError('文件大小超出明确配置的供应商字节上限')
        if not re.fullmatch('[0-9a-f]{64}', sha256):
            raise ValueError('上传必须绑定文件SHA256')
        self.source, self.byte_size, self.sha256 = source, byte_size, sha256
        boundary = 'hf-' + uuid4().hex
        self.content_type = 'multipart/form-data; boundary=' + boundary
        self.prefix = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
            f'Content-Type: {mime_type}\r\n\r\n'
        ).encode('ascii')
        self.suffix = f'\r\n--{boundary}--\r\n'.encode('ascii')
        self.content_length = len(self.prefix) + byte_size + len(self.suffix)

    async def chunks(self) -> AsyncIterator[bytes]:
        await asyncio.to_thread(self.source.seek, 0)
        yield self.prefix
        digest, remaining = hashlib.sha256(), self.byte_size
        while remaining:
            chunk = await asyncio.to_thread(self.source.read, min(CHUNK_BYTES, remaining))
            if not chunk:
                raise ValueError('上传文件已截断')
            digest.update(chunk)
            remaining -= len(chunk)
            yield chunk
        extra = await asyncio.to_thread(self.source.read, 1)
        if extra or digest.hexdigest() != self.sha256:
            raise ValueError('上传文件大小或摘要已变化')
        yield self.suffix

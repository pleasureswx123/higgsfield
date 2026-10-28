"""同步图片响应的受控落盘；字节不进入数据库、日志或队列。"""

import asyncio
import hashlib
import io
import os
from uuid import uuid4

from module_higgsfield.entity.vo.archive_file_vo import ArchiveFileFacts
from module_higgsfield.entity.vo.image_provider_fact_vo import ProviderImage
from module_higgsfield.service.storage_service import StorageService


class ImageStorageService:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    def _write(self, image: ProviderImage, declared_format: str | None, declared_size: str | None) -> dict:
        data = image.data.get_secret_value()
        if not data or len(data) > self.storage.policy.max_bytes:
            raise ValueError('生成图片超过存储字节上限')
        # 先在内存验证像素和真实类型，避免不可信文件在受控媒体目录短暂可见。
        if not (
            data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or (data[:4] == b'RIFF' and data[8:12] == b'WEBP')
        ):
            raise ValueError('生成图片不是支持的图片格式')
        metadata = self.storage.verify_media(io.BytesIO(data))
        if not metadata['mime_type'].startswith('image/'):
            raise ValueError('生成结果不是图片')
        if declared_format and metadata['mime_type'] != 'image/' + declared_format:
            raise ValueError('生成图片实际格式与供应商声明不一致')
        if declared_size and declared_size != 'auto' and declared_size != f'{metadata["width"]}x{metadata["height"]}':
            raise ValueError('生成图片实际尺寸与供应商声明不一致')
        key = 'media/' + uuid4().hex
        facts = ArchiveFileFacts(
            storage_key=key,
            sha256=hashlib.sha256(data).hexdigest(),
            byte_size=len(data),
            **metadata,
        ).model_dump()
        created = False
        try:
            with self.storage.open_key(key, write=True) as handle:
                created = True
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            return facts
        except BaseException:
            if created:
                try:
                    self.storage.remove_unbound_key(key)
                except Exception:
                    # 存储失联时保留待清理证据，不覆盖原始写入错误。
                    pass
            raise

    async def persist(
        self,
        image: ProviderImage,
        *,
        declared_format: str | None = None,
        declared_size: str | None = None,
    ) -> dict:
        task = asyncio.create_task(asyncio.to_thread(self._write, image, declared_format, declared_size))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # 线程文件IO不可被取消；等其关闭后再清理，避免与仍在写入的句柄竞争。
            # 此时调用方从未收到文件事实，因此尚未开始数据库登记。
            try:
                facts = await task
                await asyncio.to_thread(self.storage.remove_unbound_key, facts['storage_key'])
            except Exception:
                pass
            raise

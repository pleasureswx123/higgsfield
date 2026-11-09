"""固定参考图以Base64直接发送，不缩放、不上传至未核实的外部接口。"""

import asyncio
import base64
import hashlib
import io

from pydantic import SecretStr

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.image_reference_policy import validate_image_references
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.write_service import WriteService

MAX_REFERENCES = 16


class ImageReferenceService:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    async def __call__(self, context: JobExecutionContext, compiled: dict) -> dict[int, SecretStr]:
        validate_image_references(compiled['media'])
        if len(compiled['media']) > MAX_REFERENCES:
            raise ValueError('参考图最多16张')
        media = compiled['media']
        for ordinal, item in enumerate(media):
            if item['ordinal'] != ordinal or item['mediaType'] != 'image' or item['mediaRole'] != 'reference_image':
                raise ValueError('仅支持按固定顺序排列的参考图片')
        if not media:
            return {}
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if WriteService.digest(compiled) != WriteService.digest(job.input_snapshot['compiled']):
                raise ValueError('参考图与固定任务快照不一致')
            files = {file.file_id: file for file in await AssetDao.files(db, [int(item['fileId']) for item in media])}
            keys = []
            for item in media:
                file = files.get(int(item['fileId']))
                if file is None or file.state != '1' or file.sha256 != item['sha256']:
                    raise ValueError('参考图文件已不可用或版本不一致')
                keys.append(file.storage_key)
        # 文件IO不占数据库事务；最多两张同时解码，限制像素内存峰值。
        semaphore = asyncio.Semaphore(2)

        async def prepare(item, key):
            async with semaphore:
                task = asyncio.create_task(asyncio.to_thread(self._encode, item, key))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    # 线程不可强制终止，等待其关闭文件后才释放并发名额。
                    await asyncio.gather(task, return_exceptions=True)
                    raise

        tasks = [asyncio.create_task(prepare(item, key)) for item, key in zip(media, keys)]
        try:
            return dict(enumerate(await asyncio.gather(*tasks)))
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _encode(self, item: dict, key: str) -> SecretStr:
        """在同一线程完成读取、完整性校验和编码，不改变参考图原始字节。"""
        size = int(item['byteSize'])
        with self.storage.open_key(key) as handle:
            data = handle.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('参考图字节与固定版本不一致')
        metadata = self.storage.verify_media(io.BytesIO(data))
        mime = metadata['mime_type']
        if mime not in ('image/png', 'image/jpeg', 'image/webp') or mime != item['mimeType']:
            raise ValueError('参考图仅支持真实PNG、JPEG、WebP图片')
        return SecretStr(f'data:{mime};base64,' + base64.b64encode(data).decode('ascii'))

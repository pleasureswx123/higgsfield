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
from module_higgsfield.service.storage_io_service import open_source
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
        urls = {}
        for ordinal, item in enumerate(compiled['media']):
            if item['ordinal'] != ordinal or item['mediaType'] != 'image' or item['mediaRole'] != 'reference_image':
                raise ValueError('仅支持按固定顺序排列的参考图片')
            size = int(item['byteSize'])
            async with context.sessions() as db:
                job, _ = await JobLeaseService.guard(db, context.lease)
                if WriteService.digest(compiled) != WriteService.digest(job.input_snapshot['compiled']):
                    raise ValueError('参考图与固定任务快照不一致')
                file = await AssetDao.file(db, int(item['fileId']))
                if file is None or file.state != '1' or file.sha256 != item['sha256']:
                    raise ValueError('参考图文件已不可用或版本不一致')
                key = file.storage_key
            async with open_source(self.storage, key) as handle:
                data = await asyncio.to_thread(handle.read, size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('参考图字节与固定版本不一致')
            metadata = await asyncio.to_thread(self.storage.verify_media, io.BytesIO(data))
            mime = metadata['mime_type']
            if mime not in ('image/png', 'image/jpeg', 'image/webp') or mime != item['mimeType']:
                raise ValueError('参考图仅支持真实PNG、JPEG、WebP图片')
            urls[ordinal] = SecretStr(f'data:{mime};base64,' + base64.b64encode(data).decode('ascii'))
        return urls

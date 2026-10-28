"""后台发现图片并生成缩略图；只处理归档媒体，不提交供应商请求。"""
import asyncio
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.media_derivative_dao import MediaDerivativeDao as Dao
from module_higgsfield.service.media_derivative_service import MediaDerivativeService as Service
from module_higgsfield.service.image_thumbnail_service import ImageThumbnailService


class ImageThumbnailWorker:
    def __init__(self, sessions, worker, *, storage=None, batch_size=4, lease_seconds=120):
        Service.worker(worker)
        if type(batch_size) is not int or not 1 <= batch_size <= 32:
            raise ValueError('缩略图批量数须为1至32')
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 300:
            raise ValueError('缩略图租约须为5至300秒')
        self.sessions, self.worker = sessions, worker
        self.processor = ImageThumbnailService(storage)
        self.batch_size, self.lease_seconds = batch_size, lease_seconds

    async def discover(self):
        async with self.sessions() as db:
            identities = await Dao.undiscovered(db, Service.recipe, self.batch_size)
        for identity in identities:
            async with self.sessions() as db:
                try:
                    await Service.enqueue(db, identity, self.worker)
                except ServiceWarning:
                    # 发现与入队之间源可能被隔离，下次发现仍依赖权威文件状态。
                    continue

    async def handle(self):
        async with self.sessions() as db:
            claim = await Service.claim(db, self.worker, self.lease_seconds)
        if not claim:
            return {'status': 'skipped'}
        facts = None
        try:
            facts = await asyncio.to_thread(self.processor.create, claim['storageKey'], claim['sha256'],
                                            claim['byteSize'], claim['mimeType'])
            async with self.sessions() as db:
                await Service.complete(db, claim['id'], self.worker, claim['revision'], facts)
            return {'id': str(claim['id']), 'status': 'handled'}
        except Exception as error:
            if facts:
                # 锁等待原登记事务结束，数据库不可用时不猜测文件未绑定，也不删除。
                try:
                    async with self.sessions() as db:
                        row = await Dao.locked(db, claim['id'])
                        file = await Dao.by_key(db, facts['storage_key'])
                        committed = bool(file and row and row.derived_file_id == file.file_id and row.state == '2')
                        registered = file is not None
                        await db.commit()
                    if committed:
                        return {'id': str(claim['id']), 'status': 'handled'}
                    if not registered:
                        await asyncio.to_thread(self.processor.storage.remove_unbound_key, facts['storage_key'])
                except Exception:
                    return {'id': str(claim['id']), 'status': 'registration_unknown'}
            code = error.data.get('errorCode') if isinstance(error, ServiceWarning) and isinstance(error.data, dict) else None
            try:
                async with self.sessions() as db:
                    await Service.failure(db, claim['id'], self.worker, claim['revision'], code)
            except ServiceWarning:
                return {'id': str(claim['id']), 'status': 'lease_lost'}
            return {'id': str(claim['id']), 'status': 'failed'}

    async def run_once(self):
        await self.discover()
        return await asyncio.gather(*(self.handle() for _ in range(self.batch_size)))

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

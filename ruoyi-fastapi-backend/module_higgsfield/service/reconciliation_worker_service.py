"""本地对账文件执行器；文件 IO 不持有数据库事务，重复执行由导入事务去重。"""
import asyncio
import hashlib
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.service.reconciliation_import_service import ReconciliationImportService
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService
from module_higgsfield.service.storage_service import StorageService
from utils.time_util import TimezoneUtil


class ReconciliationWorker:
    def __init__(self, sessions, storage=None, *, concurrency=4, handler_timeout=300):
        if type(concurrency) is not int or not 1 <= concurrency <= 32:
            raise ValueError('对账工作器并发数必须在1到32之间')
        if type(handler_timeout) is not int or handler_timeout < 1:
            raise ValueError('对账工作器超时必须为正整数')
        self.sessions, self.storage = sessions, storage or StorageService()
        self.concurrency, self.timeout = concurrency, handler_timeout

    @staticmethod
    def snapshot(context):
        if context is None:
            raise ServiceWarning(message='账单文件关联异常', data={'errorCode': 'RECONCILIATION_FILE_INVALID'})
        batch, file, upload = context
        if (file.state != '1' or file.mime_type not in ReconciliationParserService.mime_types or upload.state != '3'
                or upload.purpose != 'reconciliation' or upload.project_id is not None
                or upload.completed_file_id != file.file_id or upload.byte_size != file.byte_size
                or upload.declared_mime_type != file.mime_type
                or upload.verified_sha256 != file.sha256 or batch.file_hash != file.sha256):
            raise ServiceWarning(message='账单文件证据不一致', data={'errorCode': 'RECONCILIATION_FILE_INVALID'})
        return (batch.account_id, file.file_id, file.storage_key, file.byte_size, file.sha256, file.mime_type)

    def read_rows(self, facts):
        _, _, key, size, digest, mime = facts
        if size > self.storage.policy.max_bytes:
            raise ServiceWarning(message='账单超过导入容量限制', data={'errorCode': 'RECONCILIATION_FILE_INVALID'})
        with self.storage.open_key(key) as handle:
            body = handle.read(size + 1)
        if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
            raise ServiceWarning(message='账单摘要校验失败', data={'errorCode': 'RECONCILIATION_FILE_INVALID'})
        parser = ReconciliationParserService.csv if mime == 'text/csv' else ReconciliationParserService.xlsx
        return parser(body, self.storage.policy.max_bytes)

    async def execute(self, batch_id):
        try:
            async with self.sessions() as db:
                batch = await Dao.batch(db, batch_id)
                if batch is None or batch.status != '0':
                    return False
                facts = self.snapshot(await Dao.file_context(db, batch_id))
            rows = await asyncio.to_thread(self.read_rows, facts)
            async with self.sessions() as db:
                await Dao.lock_account(db, facts[0])
                batch = await Dao.batch(db, batch_id, lock=True)
                if batch is None or batch.status != '0':
                    return False
                if self.snapshot(await Dao.file_context(db, batch_id)) != facts:
                    raise ServiceWarning(message='读取期间账单证据发生变化', data={'errorCode': 'RECONCILIATION_FILE_INVALID'})
                return await ReconciliationImportService.apply(db, batch_id, rows)
        except ServiceWarning as error:
            code = error.data.get('errorCode') if isinstance(error.data, dict) else None
            if code != 'RECONCILIATION_FILE_INVALID':
                raise
            # 不保存异常正文或来源内容，诊断仅保留固定码及安全行号。
            line_no = error.data.get('lineNo', 0)
            line_no = line_no if type(line_no) is int and 0 <= line_no <= 2147483647 else 0
            async with self.sessions() as db:
                batch = await Dao.batch(db, batch_id)
                if batch is None:
                    return False
                await Dao.lock_account(db, batch.account_id)
                batch = await Dao.batch(db, batch_id, lock=True)
                if batch.status != '0':
                    return False
                batch.status = '3'
                batch.import_error = {'code': code, 'lineNo': line_no,
                    'message': '账单文件或格式校验失败，请核对原始文件及标准模板'}
                batch.revision += 1
                batch.update_time = TimezoneUtil.utc_now()
                await db.commit()
            return True

    async def run_once(self):
        async with self.sessions() as db:
            ids = await Dao.candidates(db, self.concurrency)
        async def handle(identity):
            try:
                changed = await asyncio.wait_for(self.execute(identity), timeout=self.timeout)
                return {'batchId': str(identity), 'status': 'handled' if changed else 'skipped'}
            except Exception:
                try:
                    async with self.sessions() as db:
                        batch = await Dao.batch(db, identity)
                        if batch is not None:
                            await Dao.lock_account(db, batch.account_id)
                            batch = await Dao.batch(db, identity, lock=True)
                            if batch.status == '0':
                                batch.update_time = TimezoneUtil.utc_now()
                            await db.commit()
                except Exception:
                    pass
                return {'batchId': str(identity), 'status': 'failed'}
        return await asyncio.gather(*(handle(identity) for identity in ids))

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass

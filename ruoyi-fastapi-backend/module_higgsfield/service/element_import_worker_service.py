"""本地元素模板解析工作器，文件IO在事务外，写回时重新核对来源。"""
import asyncio
import hashlib
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.element_import_dao import ElementImportDao as Dao
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as Parser
from module_higgsfield.service.element_import_formats import MIME_TYPES, supports_version, parse_document
from module_higgsfield.service.element_import_result_service import ElementImportResultService
from module_higgsfield.service.storage_service import StorageService
from utils.time_util import TimezoneUtil


class ElementImportWorker:
    def __init__(self, sessions, storage=None, *, concurrency=4, handler_timeout=300):
        if type(concurrency) is not int or not 1 <= concurrency <= 32:
            raise ValueError('导入工作器并发数必须为1到32')
        if type(handler_timeout) is not int or not 1 <= handler_timeout <= 3600:
            raise ValueError('导入处理超时必须为1到3600秒')
        self.sessions, self.storage = sessions, storage or StorageService()
        self.concurrency, self.timeout = concurrency, handler_timeout

    @staticmethod
    def snapshot(context):
        if context is None:
            Parser.fail(0, '导入文件关联缺失')
        job, file, upload, binding = context
        if (file.state != '1' or upload.state != '3' or upload.purpose not in {'asset', 'element_import'}
                or upload.project_id != job.project_id or upload.owner_id != job.actor_id
                or binding.bound_by != job.actor_id or upload.completed_file_id != file.file_id
                or upload.byte_size != file.byte_size or upload.verified_sha256 != file.sha256
                or upload.expected_sha256 != file.sha256 or upload.declared_mime_type != file.mime_type
                or MIME_TYPES.get(job.source_format) != file.mime_type
                or not supports_version(job.source_format, job.parser_version) or job.schema_version != 1):
            Parser.fail(0, '导入文件或解析配置不一致')
        name = job.validation_report.get('projectName', '')
        if not isinstance(name, str) or (job.include_project_name == 'Y' and not name.strip()):
            Parser.fail(0, '导入项目名称快照缺失')
        return (file.file_id, file.storage_key, file.byte_size, file.sha256, job.source_format,
                job.parser_version, name, job.include_project_name == 'Y', job.project_id, job.actor_id)

    def read_rows(self, facts):
        _, key, size, digest, source_format, version, name, include_name, _, _ = facts
        if not 0 < size <= self.storage.policy.max_bytes:
            Parser.fail(0, '导入文件大小超过限制')
        with self.storage.open_key(key) as handle:
            body = handle.read(size + 1)
        if len(body) != size or hashlib.sha256(body).hexdigest() != digest:
            Parser.fail(0, '导入文件大小或摘要不一致')
        return parse_document(body, source_format, version=version, max_bytes=self.storage.policy.max_bytes,
                      project_name=name, include_project_name=include_name)

    async def execute(self, identity):
        try:
            async with self.sessions() as db:
                job = await Dao.job(db, identity)
                if job is None or job.status != '0':
                    return False
                facts = self.snapshot(await Dao.file_context(db, identity))
            rows = await asyncio.to_thread(self.read_rows, facts)
            async with self.sessions() as db:
                job = await Dao.job(db, identity, lock=True)
                if job is None or job.status != '0':
                    return False
                if self.snapshot(await Dao.file_context(db, identity)) != facts:
                    Parser.fail(0, '解析期间来源发生变化')
                return await ElementImportResultService.apply(db, identity, rows,
                    source_file_id=facts[0], parser_version=facts[5])
        except ServiceWarning as error:
            if not isinstance(error.data, dict) or error.data.get('errorCode') != 'ELEMENT_IMPORT_FILE_INVALID':
                raise
            line = error.data.get('lineNo', 0)
            line = line if type(line) is int and 0 <= line <= 2147483647 else 0
            async with self.sessions() as db:
                job = await Dao.job(db, identity, lock=True)
                if job is None or job.status != '0':
                    return False
                job.validation_report = dict(projectName=job.validation_report.get('projectName', ''),
                    total=0, valid=0, invalid=0, errors=[{'code': 'ELEMENT_IMPORT_FILE_INVALID', 'lineNo': line,
                        'message': '文件或模板格式校验失败，请核对原始文档'}])
                job.status, job.revision = '4', job.revision + 1
                job.update_time = TimezoneUtil.utc_now()
                await db.commit()
            return True

    async def run_once(self):
        async with self.sessions() as db:
            identities = await Dao.candidates(db, self.concurrency)

        async def handle(identity):
            try:
                changed = await asyncio.wait_for(self.execute(identity), timeout=self.timeout)
                return {'importId': str(identity), 'status': 'handled' if changed else 'skipped'}
            except Exception:
                # 存储/数据库临时异常保持待处理，推后排序避免阻塞其他批次。
                try:
                    async with self.sessions() as db:
                        job = await Dao.job(db, identity, lock=True)
                        if job is not None and job.status == '0':
                            job.update_time = TimezoneUtil.utc_now()
                            await db.commit()
                except Exception:
                    pass
                return {'importId': str(identity), 'status': 'failed'}
        return await asyncio.gather(*(handle(identity) for identity in identities))

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass

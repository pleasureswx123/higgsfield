"""真实上传至自动候选登记、并发幂等与安全失败状态。"""
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from module_higgsfield.entity.vo.element_import_vo import ElementImportCreate
from module_higgsfield.service.element_import_service import ElementImportService
from module_higgsfield.service.element_import_worker_service import ElementImportWorker
from tests import test_higgsfield_element_import_upload as uploads


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportWorkerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = uploads.ElementImportUploadTests.asyncSetUp
    cleanup_schema = uploads.ElementImportUploadTests.cleanup_schema
    create = uploads.ElementImportUploadTests.create
    migrate = uploads.ElementImportUploadTests.migrate
    send_part = uploads.ElementImportUploadTests.send_part
    upload = uploads.ElementImportUploadTests.upload

    async def accept(self, body, mime='text/csv'):
        upload_id, _ = await self.upload(body, mime)
        async with self.sessions() as db:
            response, _ = await ElementImportService.create(db, self.owner,
                ElementImportCreate(projectId=self.project_id, uploadId=str(upload_id), schemaVersion=1), str(uuid4()))
        return int(response['data']['id'])

    async def test_text_and_markdown_upload_parse_and_register_real_rows(self):
        for mime, body in [('text/plain', '角色：记者\n人物描述\n场景：车站'),
                           ('text/markdown', '## 道具：笔记本\n文字说明\n## 其他：海报')]:
            identity = await self.accept(body.encode(), mime)
            self.assertTrue(await ElementImportWorker(self.sessions, self.storage).execute(identity))
            async with self.sessions() as db:
                detail = await ElementImportService.get(db, self.owner, identity)
                self.assertEqual(detail['status'], 'validated')
                self.assertEqual(detail['summary'], {'total': 2, 'valid': 2, 'invalid': 0})
                rows = (await db.execute(text('SELECT source_locator, candidate FROM hf_import_row '
                    'WHERE import_job_id=:id ORDER BY row_no'), {'id': identity})).all()
                self.assertEqual([row.source_locator['line'] for row in rows], [1, 3])
                self.assertEqual(rows[0].candidate['description'], body.splitlines()[1])

    async def test_docx_real_upload_and_paragraph_locations(self):
        from tests.test_higgsfield_element_docx_parser import docx
        from module_higgsfield.service.docx_content_service import DocxContentService
        body = docx('<w:p><w:r><w:t>角色：记者</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>人物描述</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>场景：车站</w:t></w:r></w:p>')
        identity = await self.accept(body, DocxContentService.mime)
        self.assertTrue(await ElementImportWorker(self.sessions, self.storage).execute(identity))
        async with self.sessions() as db:
            self.assertEqual((await ElementImportService.get(db, self.owner, identity))['status'], 'validated')
            rows = (await db.execute(text('SELECT source_locator FROM hf_import_row WHERE import_job_id=:id '
                                          'ORDER BY row_no'), {'id': identity})).scalars().all()
            self.assertEqual(rows, [{'paragraph': 1, 'line': 1}, {'paragraph': 3, 'line': 1}])

    async def test_pdf_real_upload_and_page_locations(self):
        from tests.test_higgsfield_element_pdf_parser import pdf_pages
        identity = await self.accept(pdf_pages(['角色：记者\n人物描述', '场景：车站']), 'application/pdf')
        self.assertTrue(await ElementImportWorker(self.sessions, self.storage).execute(identity))
        async with self.sessions() as db:
            self.assertEqual((await ElementImportService.get(db, self.owner, identity))['status'], 'validated')
            rows = (await db.execute(text('SELECT source_locator FROM hf_import_row WHERE import_job_id=:id '
                                          'ORDER BY row_no'), {'id': identity})).scalars().all()
            self.assertEqual(rows, [{'page': 1, 'line': 1}, {'page': 2, 'line': 1}])

    async def test_screenplay_fixed_new_version_and_legacy_retry(self):
        body = '角色：甲\n内景：车站\n甲：你好'.encode()
        current = await self.accept(body, 'text/plain')
        legacy = await self.accept(body, 'text/plain')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT parser_version FROM hf_import_job WHERE import_id=:id'),
                                            {'id': current}), 'element-screenplay-v2')
            await db.execute(text("UPDATE hf_import_job SET parser_version='element-text-v1' WHERE import_id=:id"), {'id': legacy})
            await db.commit()
        worker = ElementImportWorker(self.sessions, self.storage)
        self.assertTrue(await worker.execute(current))
        self.assertTrue(await worker.execute(legacy))
        async with self.sessions() as db:
            self.assertEqual((await ElementImportService.get(db, self.owner, current))['summary']['total'], 3)
            self.assertEqual((await ElementImportService.get(db, self.owner, legacy))['summary']['total'], 1)

    async def test_concurrent_workers_keep_project_name_snapshot_and_one_candidate_set(self):
        identity = await self.accept('名称,别名,分类,描述\n角色,001,角色,说明\n,002,场景,待修正'.encode())
        async with self.sessions() as db:
            name = await db.scalar(text('SELECT project_name FROM hf_project'))
            await db.execute(text("UPDATE hf_project SET project_name='后来的项目名'"))
            await db.commit()
        worker = ElementImportWorker(self.sessions, self.storage)
        self.assertEqual(sorted(await asyncio.gather(worker.execute(identity), worker.execute(identity))), [False, True])
        async with self.sessions() as db:
            detail = await ElementImportService.get(db, self.owner, identity)
            self.assertEqual(detail['status'], 'validated')
            self.assertEqual(detail['summary'], {'total': 2, 'valid': 1, 'invalid': 1})
            alias = await db.scalar(text("SELECT candidate->>'alias' FROM hf_import_row WHERE row_no=1"))
            self.assertEqual(alias, name + '_001')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row')), 2)
        self.assertEqual(await worker.run_once(), [])

    async def test_format_failure_is_terminal_but_storage_failure_can_retry(self):
        invalid = await self.accept(b'wrong,header\na,b')
        valid = await self.accept(b'name,alias,category,description\na,001,prop,description')
        worker = ElementImportWorker(self.sessions, self.storage)
        with patch.object(self.storage, 'open_key', side_effect=OSError('模拟临时存储故障')):
            results = await worker.run_once()
        self.assertEqual([row['status'] for row in results], ['failed', 'failed'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_job WHERE status='0'")), 2)
        self.assertTrue(await worker.execute(invalid))
        self.assertTrue(await worker.execute(valid))
        async with self.sessions() as db:
            detail = await ElementImportService.get(db, self.owner, invalid)
            self.assertEqual(detail['status'], 'failed')
            self.assertEqual(detail['errors'][0]['code'], 'ELEMENT_IMPORT_FILE_INVALID')
            self.assertNotIn('wrong', str(detail))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row WHERE import_job_id=:id'), {'id': invalid}), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row WHERE import_job_id=:id'), {'id': valid}), 1)
        self.assertFalse(await worker.execute(invalid))

    async def test_changed_file_bytes_fail_before_candidate_registration(self):
        body = b'name,alias,category,description\na,001,prop,description'
        identity = await self.accept(body)
        async with self.sessions() as db:
            key = await db.scalar(text('SELECT f.storage_key FROM hf_import_job j JOIN hf_stored_file f '
                'ON f.file_id=j.source_file_id WHERE j.import_id=:id'), {'id': identity})
        (Path(self.directory.name) / key).write_bytes(body.replace(b'001', b'002'))
        worker = ElementImportWorker(self.sessions, self.storage)
        self.assertTrue(await worker.execute(identity))
        async with self.sessions() as db:
            self.assertEqual((await ElementImportService.get(db, self.owner, identity))['status'], 'failed')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row')), 0)

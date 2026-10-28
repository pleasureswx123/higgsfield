"""整批确认复用元素规则，冲突及审计失败不留下半批数据。"""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.vo.element_import_vo import ElementImportConfirm, ElementImportRowEdit
from module_higgsfield.entity.vo.element_vo import ElementCreate
from module_higgsfield.service.element_import_confirm_service import ElementImportConfirmService
from module_higgsfield.service.element_import_worker_service import ElementImportWorker
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.element_import_edit_service import ElementImportEditService
from tests import test_higgsfield_element_import_worker as worker


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportConfirmTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.ElementImportWorkerTests.cleanup_schema
    create = worker.ElementImportWorkerTests.create
    migrate = worker.ElementImportWorkerTests.migrate
    send_part = worker.ElementImportWorkerTests.send_part
    upload = worker.ElementImportWorkerTests.upload
    accept = worker.ElementImportWorkerTests.accept

    async def test_all_document_formats_create_elements_after_real_upload_and_parse(self):
        from tests.test_higgsfield_element_docx_parser import docx
        from tests.test_higgsfield_element_pdf_parser import pdf_pages
        from module_higgsfield.service.docx_content_service import DocxContentService
        from io import BytesIO
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(['名称', '别名', '分类', '描述'])
        book.active.append(['XLSX车站', 'xlsx_station', '场景', '车站描述'])
        book.active.append(['XLSX记者', 'xlsx_reporter', '角色', '记者描述'])
        stream = BytesIO()
        book.save(stream)
        book.close()
        documents = [
            ('text/csv', '名称,别名,分类,描述\nCSV车站,csv_station,场景,车站描述\nCSV记者,csv_reporter,角色,记者描述'.encode()),
            ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', stream.getvalue()),
            ('text/plain', '内景：TXT车站\nTXT记者：你好'.encode()),
            ('text/markdown', '内景：MD车站\nMD记者：你好'.encode()),
            (DocxContentService.mime, docx('<w:p><w:r><w:t>内景：DOCX车站</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>DOCX记者：你好</w:t></w:r></w:p>')),
            ('application/pdf', pdf_pages(['内景：PDF车站', 'PDF记者：你好'])),
        ]
        for mime, body in documents:
            with self.subTest(mime=mime):
                identity = await self.accept(body, mime)
                self.assertTrue(await ElementImportWorker(self.sessions, self.storage).execute(identity))
                async with self.sessions() as db:
                    response, _ = await ElementImportConfirmService.confirm(db, self.owner, identity,
                        ElementImportConfirm(revision='2'), str(uuid4()))
                    self.assertEqual(response['data']['createdCount'], 2)
                    self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_row WHERE import_job_id=:id AND state='1' AND element_id IS NOT NULL"), {'id': identity}), 2)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 12)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 12)

    async def asyncSetUp(self):
        await worker.ElementImportWorkerTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('confirm_elements',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_07_elements.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'element:create','project' FROM hf_project_role WHERE code='owner'"))
            await db.commit()
        self.identity = await self.accept('名称,别名,分类,描述\n角色,a,角色,角色说明\n场景,b,场景,场景说明'.encode())
        await ElementImportWorker(self.sessions, self.storage).execute(self.identity)

    async def confirm(self, key, revision='2'):
        async with self.sessions() as db:
            return await ElementImportConfirmService.confirm(db, self.owner, self.identity,
                                                             ElementImportConfirm(revision=revision), key)

    async def test_empty_selection_stale_confirmation_and_excluded_rows(self):
        async with self.sessions() as db:
            candidates = (await db.execute(text('SELECT row_no,candidate FROM hf_import_row ORDER BY row_no'))).all()
        for number, candidate in candidates:
            async with self.sessions() as db:
                await ElementImportEditService.edit(db, self.owner, self.identity, number,
                    ElementImportRowEdit(revision='1', candidate=candidate, isSelected=False), str(uuid4()))
        with self.assertRaises(ServiceWarning):
            await self.confirm(str(uuid4()), revision='4')
        async with self.sessions() as db:
            await ElementImportEditService.edit(db, self.owner, self.identity, 1,
                ElementImportRowEdit(revision='2', candidate=candidates[0][1], isSelected=True), str(uuid4()))
        with self.assertRaises(ServiceWarning):
            await self.confirm(str(uuid4()))
        result, _ = await self.confirm(str(uuid4()), revision='5')
        self.assertEqual(result['data']['createdCount'], 1)
        async with self.sessions() as db:
            self.assertIsNone(await db.scalar(text('SELECT element_id FROM hf_import_row WHERE row_no=2')))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 1)

    async def test_confirm_creates_fixed_revisions_once_and_rechecks_permissions(self):
        key = str(uuid4())
        first, repeated = await self.confirm(key)
        self.assertFalse(repeated)
        self.assertEqual(first['data']['createdCount'], 2)
        second, repeated = await self.confirm(key)
        self.assertTrue(repeated)
        self.assertEqual(first, second)
        third, _ = await self.confirm(str(uuid4()))
        self.assertEqual(third['data'], first['data'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 2)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_row WHERE state='1' AND element_id IS NOT NULL")), 2)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='confirm'")), 1)
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_import_job')), '3')
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.confirm(key)

    async def test_second_alias_conflict_rolls_back_first_created_element(self):
        async with self.sessions() as db:
            alias = await db.scalar(text("SELECT candidate->>'alias' FROM hf_import_row WHERE row_no=2"))
            await ElementService.create(db, self.owner, ElementCreate(projectId=self.project_id,
                name='既有场景', alias=alias, category='scene'), str(uuid4()))
        with self.assertRaises(ServiceWarning):
            await self.confirm(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row WHERE element_id IS NOT NULL')), 0)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_import_job')), 2)

    async def test_audit_failure_rolls_back_all_elements_and_can_retry(self):
        with patch.object(AssetDao, 'add', AsyncMock(side_effect=RuntimeError('模拟审计失败'))):
            with self.assertRaises(RuntimeError):
                await self.confirm(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 0)
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_import_job')), '1')
        self.assertEqual((await self.confirm(str(uuid4())))[0]['data']['createdCount'], 2)

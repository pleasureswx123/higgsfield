"""导入受理绑定、权限重验和候选分页的真实数据库验证。"""
import importlib.util
import os
from pathlib import Path
from datetime import timedelta
from uuid import uuid4
import unittest
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.do.asset_do import HfStoredFile, HfUploadSession
from module_higgsfield.entity.vo.element_import_vo import ElementImportCreate, ElementImportRowsQuery
from module_higgsfield.service.element_import_service import ElementImportService as Service
from module_higgsfield.service.element_import_result_service import ElementImportResultService
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as Parser
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_assets as assets
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        for name in ('20261027_16_audit.py', '20261028_66_element_imports.py'):
            spec = importlib.util.spec_from_file_location('import_service', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'element:import','project' FROM hf_project_role WHERE code='owner'"))
            file = HfStoredFile(storage_key='documents/test.csv', sha256='a'*64, byte_size=100,
                                mime_type='text/csv', state='1', **audit)
            db.add(file)
            await db.flush()
            self.file_id = file.file_id
            upload = HfUploadSession(owner_id=1, project_id=int(self.project_id), purpose='asset', file_name='元素.csv',
                declared_mime_type='text/csv', byte_size=100, part_size=100, part_count=1,
                expected_sha256='a'*64, verified_sha256='a'*64, completed_file_id=file.file_id,
                state='3', expires_time=audit['create_time']+timedelta(days=1), validation_errors=[], **audit)
            db.add(upload)
            await db.flush()
            self.payload = ElementImportCreate(projectId=self.project_id, uploadId=str(upload.upload_id), schemaVersion=1)
            await db.commit()

    async def accept(self, key):
        async with self.sessions() as db:
            return await Service.create(db, self.owner, self.payload, key)

    async def test_binding_replay_filtered_rows_and_revocation(self):
        key = str(uuid4())
        first, repeated = await self.accept(key)
        self.assertFalse(repeated)
        second, repeated = await self.accept(key)
        self.assertTrue(repeated)
        self.assertEqual(first, second)
        identity = int(first['data']['id'])
        with self.assertRaises(ServiceWarning):
            await self.accept(str(uuid4()))
        rows = Parser.csv('名称,别名,分类,描述\n角色,a,角色,说明\n,b,道具,待修正'.encode(), max_bytes=10000)
        async with self.sessions() as db:
            await ElementImportResultService.apply(db, identity, rows, source_file_id=self.file_id, parser_version=Parser.version)
            summary = await Service.get(db, self.owner, identity)
            self.assertEqual(summary['summary'], {'total': 2, 'valid': 1, 'invalid': 1})
            self.assertNotIn('parseHash', str(summary))
            page = await Service.rows(db, self.owner, identity, ElementImportRowsQuery(state='failed', pageSize=1))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['rowNo'], 2)
            self.assertTrue(page.rows[0]['issues'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_upload_binding')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='element_import'")), 1)
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.accept(key)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await Service.rows(db, self.owner, identity, ElementImportRowsQuery())

    async def test_foreign_upload_and_inconsistent_file_cannot_bind(self):
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_upload_session SET owner_id=2'))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.accept(str(uuid4()))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_upload_session SET owner_id=1,verified_sha256=repeat('b',64),expected_sha256=repeat('b',64)"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.accept(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_job')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_upload_binding')), 0)

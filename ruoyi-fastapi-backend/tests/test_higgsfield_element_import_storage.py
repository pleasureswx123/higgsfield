"""真实迁移验证导入去重、候选结构、确认结果约束与审计字段。"""
import importlib.util
import os
from pathlib import Path
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.element_import_do import HfImportJob, HfImportRow
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('element_imports',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_66_element_imports.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.audit = WriteService.audit(self.owner)

    async def test_request_identity_and_candidate_confirmation_constraints(self):
        values = dict(project_id=1, actor_id=1, source_file_id=1, schema_version=1,
            source_format='csv', parser_version='table-v1', idempotency_key='a' * 64, **self.audit)
        async with self.sessions() as db:
            job = HfImportJob(**values)
            db.add(job)
            await db.flush()
            for changes in ({}, {'idempotency_key': 'format', 'source_format': 'exe'},
                            {'idempotency_key': 'schema', 'schema_version': 0},
                            {'idempotency_key': 'report', 'validation_report': []},
                            {'idempotency_key': 'revision', 'revision': 0}):
                with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfImportJob(**(values | changes)))
                        await db.flush()
            row_values = dict(import_job_id=job.import_id, row_no=1, candidate={'schemaVersion': 1, 'name': '角色'},
                              source_locator={'line': 2}, **self.audit)
            row = HfImportRow(**row_values)
            db.add(row)
            await db.flush()
            for changes in ({}, {'row_no': 0}, {'row_no': 2, 'candidate': []},
                            {'row_no': 2, 'source_locator': []}, {'row_no': 2, 'revision': 0},
                            {'row_no': 2, 'state': '1'}, {'row_no': 2, 'element_id': 1},
                            {'row_no': 2, 'state': '1', 'element_id': 1, 'is_selected': 'N'},
                            {'row_no': 2, 'state': '1', 'element_id': 1, 'error_code': 'FAILED'}):
                with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfImportRow(**(row_values | changes)))
                        await db.flush()
            row.state, row.element_id = '1', 9007199254740993
            await db.flush()
            self.assertEqual(row.element_id, 9007199254740993)
            for table in ('hf_import_job', 'hf_import_row'):
                self.assertEqual(await db.scalar(text(
                    "SELECT count(*) FROM pg_constraint WHERE conrelid=CAST(:table AS regclass) AND contype='f'"
                ), {'table': table}), 0)
                self.assertEqual(await db.scalar(text(
                    "SELECT count(*) FROM pg_attribute WHERE attrelid=CAST(:table AS regclass) "
                    "AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                ), {'table': table}), 0)
                self.assertTrue(await db.scalar(text("SELECT obj_description(CAST(:table AS regclass),'pg_class')"),
                                                {'table': table}))
            await db.rollback()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_job')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row')), 0)

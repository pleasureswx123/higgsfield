"""凭据测试证据真实迁移和状态约束，不能把待执行记录作为通过证据。"""
import importlib.util
import os
import unittest
from pathlib import Path
from datetime import datetime, UTC
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from tests import test_higgsfield_projects as projects
from module_higgsfield.entity.do.credential_test_do import HfCredentialTest


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location('credential_test_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_57_credential_tests.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade()
            await conn.run_sync(migrate)

    def record(self, **changes):
        now = datetime.now(UTC)
        return HfCredentialTest(**(dict(credential_version_id=1, connection_version_id=2,
            cost_center_id=3, requested_by=1, config_hash='a'*64, result={},
            create_time=now, update_time=now) | changes))

    async def test_pending_and_terminal_evidence(self):
        async with self.sessions() as db:
            row = self.record()
            db.add(row)
            await db.commit()
            self.assertEqual(row.state, '0')
            self.assertIsNone(row.provider_call_id)
            row.state, row.provider_call_id, row.finished_time = '1', 9, datetime.now(UTC)
            row.result = {'authentication': 'passed'}
            await db.commit()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_test')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_credential_test'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_credential_test'::regclass AND contype='f'")), 0)

    async def test_invalid_completed_state_hash_and_scope_rejected(self):
        for changes in ({'state': '1'}, {'state': '1', 'finished_time': datetime.now(UTC)},
                        {'state': '0', 'finished_time': datetime.now(UTC)},
                        {'config_hash': 'bad'}, {'result': []}, {'cost_center_id': 0}, {'requested_by': 0}):
            async with self.sessions() as db:
                with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                    db.add(self.record(**changes))
                    await db.commit()
                await db.rollback()

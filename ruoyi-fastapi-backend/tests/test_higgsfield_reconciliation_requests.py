"""真实上传与对账受理的事务、幂等及用途隔离。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from pydantic import ValidationError
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.reconciliation_vo import ReconciliationCreate
from module_higgsfield.service.reconciliation_service import ReconciliationService
from tests import test_higgsfield_price_attachments as attachments


class ReconciliationInputTests(unittest.TestCase):
    def test_period_and_precision(self):
        values = dict(accountId='1', uploadId='2', periodStart='2026-01-01T00:00:00Z', periodEnd='2026-02-01T00:00:00Z')
        self.assertEqual(ReconciliationCreate(**values).account_id, '1')
        for changes in ({'periodStart': values['periodEnd']}, {'periodStart': '2026-01-01T00:00:00'},
                {'periodStart': '2026-01-01T00:00:00.000001Z'}):
            with self.assertRaises(ValidationError):
                ReconciliationCreate(**(values | changes))


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationRequestTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = attachments.PriceAttachmentTests.cleanup_schema
    upload = attachments.PriceAttachmentTests.upload

    async def asyncSetUp(self):
        await attachments.PriceAttachmentTests.asyncSetUp(self)
        self.sessions.configure(autoflush=False)
        self.body = b'externalLineKey,currency,amount\nkey,USD,1.25\n'
        spec = importlib.util.spec_from_file_location('reconciliation',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_61_reconciliation.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as connection:
            def migrate(sync_connection):
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()
            await connection.run_sync(migrate)
            spec = importlib.util.spec_from_file_location('reconciliation_error_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_63_reconciliation_import_error.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            await connection.run_sync(migrate)
            spec = importlib.util.spec_from_file_location('reconciliation_resolution',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_65_reconciliation_resolution.py')
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            await connection.run_sync(migrate)

    def payload(self, upload_id):
        return ReconciliationCreate(accountId=str(self.account_id), uploadId=str(upload_id),
            periodStart='2026-01-01T00:00:00Z', periodEnd='2026-02-01T00:00:00Z')

    async def test_permission_migration_is_idempotent(self):
        spec = importlib.util.spec_from_file_location('reconciliation_permission',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_62_reconciliation_permission.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as connection:
            def migrate(sync_connection):
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()
                    migration.upgrade()
            await connection.run_sync(migrate)
            self.assertEqual(await connection.scalar(text("SELECT count(*) FROM sys_menu WHERE perms='billing:reconcile'")), 1)

    async def test_receipt_binding_replay_and_duplicate_file(self):
        upload_id = await self.upload(purpose='reconciliation')
        key = str(uuid4())
        async with self.sessions() as db:
            first, _ = await ReconciliationService.create(db, self.owner, self.payload(upload_id), key)
            repeated, replay = await ReconciliationService.create(db, self.owner, self.payload(upload_id), key)
            self.assertTrue(replay)
            self.assertEqual(first, repeated)
            self.assertEqual(first['data']['state'], 'pending')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_batch')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_observation')), 0)
            self.assertEqual(await db.scalar(text('SELECT reconciliation_batch_id FROM hf_upload_binding')), int(first['data']['id']))
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await ReconciliationService.create(db, self.owner, self.payload(upload_id), key)
        self.owner.permissions = ['*:*:*']
        duplicate = await self.upload(purpose='reconciliation')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning) as error:
                await ReconciliationService.create(db, self.owner, self.payload(duplicate), str(uuid4()))
            self.assertEqual(error.exception.data['errorCode'], 'RECONCILIATION_FILE_DUPLICATE')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_upload_binding')), 1)

    async def test_wrong_purpose_not_ready_and_other_owner(self):
        wrong = await self.upload()
        incomplete = await self.upload(purpose='reconciliation', complete=False)
        other = await self.upload(purpose='reconciliation')
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_upload_session SET owner_id=2 WHERE upload_id=:id'), {'id': other})
            await db.commit()
            for identity in (wrong, incomplete, other):
                with self.assertRaises(ServiceWarning):
                    await ReconciliationService.create(db, self.owner, self.payload(identity), str(uuid4()))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_batch')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_upload_binding')), 0)

"""独立 PostgreSQL schema 中验证实际迁移及账单身份约束。"""
import importlib.util
import os
import unittest
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationBatch, HfReconciliationLine, HfReconciliationObservation
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        self.sessions.configure(autoflush=False)
        spec = importlib.util.spec_from_file_location('reconciliation_migration',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_61_reconciliation.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location('reconciliation_error_migration',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_63_reconciliation_import_error.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.audit = WriteService.audit(self.owner)
        spec = importlib.util.spec_from_file_location('reconciliation_resolution',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_65_reconciliation_resolution.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_identity_money_and_observation_constraints(self):
        now = self.audit['create_time']
        batch = dict(account_id=1, period_start=now, period_end=now+timedelta(days=1),
            source_file_id=1, file_hash='a'*64, **self.audit)
        line = dict(batch_id=1, account_id=1, line_no=2, external_line_key='0001', currency='USD',
            amount=Decimal('-0.0000000001'), raw_line={'amount': '-0.0000000001'}, **self.audit)
        observation = dict(batch_id=2, line_no=2, canonical_line_id=1, outcome='conflict',
            raw_line={'externalLineKey': '0001', 'amount': '9.99'}, **self.audit)
        async with self.sessions() as db:
            db.add_all([HfReconciliationBatch(**batch), HfReconciliationLine(**line), HfReconciliationObservation(**observation)])
            await db.flush()
            for model, value in (
                (HfReconciliationBatch, batch),
                (HfReconciliationBatch, batch | {'file_hash': 'b'*64, 'period_end': now}),
                (HfReconciliationLine, line | {'batch_id': 2}),
                (HfReconciliationLine, line | {'line_no': 3, 'external_line_key': 'other', 'status': '2'}),
                (HfReconciliationLine, line | {'line_no': 3, 'external_line_key': 'nan', 'amount': Decimal('NaN')}),
                (HfReconciliationLine, line | {'line_no': 3, 'external_line_key': 'partial', 'accepted_observation_id': 1}),
                (HfReconciliationLine, line | {'line_no': 3, 'external_line_key': 'bad-accepted',
                    'accepted_observation_id': 1, 'accepted_currency': 'USD', 'accepted_amount': Decimal('NaN')}),
                (HfReconciliationObservation, observation),
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(model(**value))
                        await db.flush()
            self.assertEqual(await db.scalar(text('SELECT amount FROM hf_reconciliation_line')), Decimal('-0.0000000001'))
            db.add(HfReconciliationBatch(**(batch | {'file_hash': 'c'*64})))
            await db.flush()

    async def test_comments_no_foreign_keys_and_protected_downgrade(self):
        async with self.sessions() as db:
            for table in ('hf_reconciliation_batch', 'hf_reconciliation_line', 'hf_reconciliation_observation'):
                self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid=CAST(:t AS regclass) AND contype='f'"), {'t': table}), 0)
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM pg_attribute WHERE attrelid=CAST(:t AS regclass) AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL'), {'t': table}), 0)
        with self.assertRaises(RuntimeError):
            await self.migrate('downgrade')

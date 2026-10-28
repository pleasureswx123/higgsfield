"""计价事实真实迁移：未知金额、分口径唯一、明细和有符号调整约束。"""

import importlib.util
import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_higgsfield.entity.do.billing_do import HfBillingEvent, HfBillingLineItem, HfBillingAdjustment
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BillingStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'billing_facts', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_39_billing_facts.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        now = datetime.now(UTC)
        self.audit = dict(create_by='test', update_by='test', create_time=now, update_time=now)

    async def test_unknown_amount_and_two_valuation_purposes(self):
        values = dict(subject_id=1, purpose='platform', price_version_id=2, currency='USD', **self.audit)
        async with self.sessions() as db:
            db.add(HfBillingEvent(**values))
            await db.flush()
            self.assertIsNone(await db.scalar(text('SELECT amount FROM hf_billing_event')))
            for change in ({}, {'subject_id': 2, 'state': '1'}, {'subject_id': 2, 'amount': Decimal('-1')}):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfBillingEvent(**(values | change)))
                        await db.flush()
            db.add(HfBillingEvent(**(values | {'purpose': 'procurement', 'state': '1', 'amount': Decimal('0')})))
            await db.flush()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_event')), 2)

    async def test_lines_adjustments_and_evidence_schema(self):
        line = dict(
            event_id=1,
            rule_item_id=2,
            quantity=Decimal('1'),
            unit_quantity=Decimal('1000000'),
            unit_price=Decimal('5'),
            amount=Decimal('0.000005'),
            calculation_snapshot={},
            **self.audit,
        )
        adjustment = dict(
            event_id=1, adjustment_key='usage:2', delta_amount=Decimal('-0.000001'), reason='依据用量修订', **self.audit
        )
        async with self.sessions() as db:
            db.add_all([HfBillingLineItem(**line), HfBillingAdjustment(**adjustment)])
            await db.flush()
            for model, values in (
                (HfBillingLineItem, line),
                (HfBillingLineItem, line | {'rule_item_id': 3, 'unit_quantity': 0}),
                (HfBillingAdjustment, adjustment),
                (HfBillingAdjustment, adjustment | {'adjustment_key': 'zero', 'delta_amount': 0}),
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(model(**values))
                        await db.flush()
            self.assertEqual(
                await db.scalar(text('SELECT delta_amount FROM hf_billing_adjustment')), Decimal('-0.000001')
            )
            for table in ('hf_billing_event', 'hf_billing_line_item', 'hf_billing_adjustment'):
                self.assertEqual(
                    await db.scalar(
                        text(
                            "SELECT count(*) FROM pg_constraint WHERE conrelid=CAST(:name AS regclass) AND contype='f'"
                        ),
                        {'name': table},
                    ),
                    0,
                )
                self.assertEqual(
                    await db.scalar(
                        text(
                            'SELECT count(*) FROM pg_attribute WHERE attrelid=CAST(:name AS regclass) AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL'
                        ),
                        {'name': table},
                    ),
                    0,
                )

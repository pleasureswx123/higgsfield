"""实际计价落库、幂等、修订争议和外层事务回滚。"""

import importlib.util
import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from module_higgsfield.entity.do.price_do import HfPriceBook, HfPriceVersion, HfPriceRuleItem
from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationLine
from module_higgsfield.service.billing_calculation_service import BillingCalculationService
from module_higgsfield.service.billing_adjustment_service import BillingAdjustmentService
from module_higgsfield.entity.vo.billing_adjustment_vo import BillingAdjustmentInput
from exceptions.exception import ServiceWarning
from tests import test_higgsfield_billing_storage as storage
from tests import test_higgsfield_job_storage as jobs


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BillingCalculationTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.BillingStorageTests.cleanup_schema
    migrate = storage.BillingStorageTests.migrate
    job = jobs.JobStorageTests.job

    async def test_adjustment_reconciliation_evidence(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db)
            event, _ = await self.calculate(db, job, subject)
            line = HfReconciliationLine(batch_id=1, account_id=subject.account_id,
                line_no=2, external_line_key='invoice-01', subject_id=subject.subject_id,
                currency=event.currency, amount=Decimal('0.01'), status='2', raw_line={}, **self.audit)
            db.add(line)
            await db.flush()
            payload = BillingAdjustmentInput(revision=str(event.revision), deltaAmount='-0.01',
                reason='核对账单', reconciliationLineId=str(line.line_id))
            args = dict(job=job, event_id=event.event_id, payload=payload, business_key='invoice:1',
                actor_id=1, now=self.now, actor='test')
            for field, value in [('status', '1'), ('status', '3'), ('account_id', 999),
                                 ('subject_id', 999), ('currency', 'CNY')]:
                original = getattr(line, field)
                setattr(line, field, value)
                await db.flush()
                with self.assertRaises(ServiceWarning) as caught:
                    await BillingAdjustmentService.append(db, **args)
                self.assertEqual(caught.exception.data['errorCode'], 'BILLING_RECONCILIATION_MISMATCH')
                setattr(line, field, original)
                await db.flush()
            # 人工采用修订币种后，调整依据按采用币种校验，原币种仍保留。
            line.currency = 'CNY'
            line.accepted_observation_id = 1
            line.accepted_currency = event.currency
            line.accepted_amount = Decimal('0')
            await db.flush()
            row, changed = await BillingAdjustmentService.append(db, **args)
            self.assertTrue(changed)
            self.assertEqual(row.reconciliation_line_id, line.line_id)
            self.assertEqual(event.amount, Decimal('0.02'))
            self.assertFalse((await BillingAdjustmentService.append(db, **args))[1])
            with self.assertRaises(ServiceWarning) as caught:
                await BillingAdjustmentService.append(db, **(args | {
                    'payload': payload.model_copy(update={'reconciliation_line_id': None})}))
            self.assertEqual(caught.exception.data['errorCode'], 'IDEMPOTENCY_KEY_REUSED')

    async def test_adjustment_preserves_original_and_deduplicates_business_key(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db)
            event, _ = await self.calculate(db, job, subject)
            payload = BillingAdjustmentInput(revision=str(event.revision), deltaAmount='-0.01', reason='部分退款')
            args = dict(
                job=job,
                event_id=event.event_id,
                payload=payload,
                business_key='refund:1',
                actor_id=1,
                now=self.now,
                actor='test',
            )
            row, changed = await BillingAdjustmentService.append(db, **args)
            self.assertTrue(changed)
            repeated, changed = await BillingAdjustmentService.append(db, **args)
            self.assertFalse(changed)
            self.assertEqual(row.adjustment_id, repeated.adjustment_id)
            self.assertEqual(event.amount, Decimal('0.02'))
            with self.assertRaises(ServiceWarning):
                await BillingAdjustmentService.append(db, **(args | {'business_key': 'refund:2'}))
            with self.assertRaises(ServiceWarning):
                await BillingAdjustmentService.append(
                    db, **(args | {'payload': payload.model_copy(update={'delta_amount': '-0.02'})})
                )
            too_much = BillingAdjustmentInput(revision=str(event.revision), deltaAmount='-0.02', reason='超额退款')
            with self.assertRaises(ServiceWarning):
                await BillingAdjustmentService.append(db, **(args | {'business_key': 'refund:3', 'payload': too_much}))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 1)
            await db.rollback()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 0)

    async def test_unknown_fee_rejects_adjustment(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db, tokens=None)
            event, _ = await self.calculate(db, job, subject)
            with self.assertRaises(ServiceWarning) as caught:
                await BillingAdjustmentService.append(
                    db,
                    job=job,
                    event_id=event.event_id,
                    payload=BillingAdjustmentInput(revision=str(event.revision), deltaAmount='1', reason='不能补零'),
                    business_key='unknown',
                    actor_id=1,
                    now=self.now,
                    actor='test',
                )
            self.assertEqual(caught.exception.data['errorCode'], 'BILLING_AMOUNT_UNKNOWN')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 0)

    async def asyncSetUp(self):
        await storage.BillingStorageTests.asyncSetUp(self)
        for name in ('20261027_22_prices.py', '20261027_27_budgets.py', '20261027_38_usage_records.py',
                     '20261028_61_reconciliation.py', '20261028_63_reconciliation_import_error.py',
                     '20261028_65_reconciliation_resolution.py'):
            spec = importlib.util.spec_from_file_location(
                'billing_setup', Path(__file__).resolve().parents[1] / 'alembic/versions' / name
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.now = datetime.now(UTC)
        self.sessions.configure(autoflush=False)

    async def seed(self, db, *, tokens=3):
        job = self.job()
        db.add(job)
        book = HfPriceBook(model_variant_id=1, purpose='platform', currency='USD', price_book_name='测试', **self.audit)
        db.add(book)
        await db.flush()
        version = HfPriceVersion(
            price_book_id=book.price_book_id,
            version_no=1,
            status='1',
            rounding_mode='half_up',
            calculation_scale=2,
            create_user_id=1,
            **self.audit,
        )
        db.add(version)
        await db.flush()
        job.platform_price_version_id = version.price_version_id
        db.add(
            HfPriceRuleItem(
                price_version_id=version.price_version_id,
                item_code='input',
                unit='token',
                unit_quantity=Decimal('2'),
                unit_price=Decimal('0.01'),
                quantity_from=0,
                formula_template='linear',
                **self.audit,
            )
        )
        subject = HfBillingSubject(
            account_id=1,
            job_id=job.job_id,
            origin_call_id=1,
            subject_kind='generation',
            identity_key='call:1',
            **self.audit,
        )
        db.add(subject)
        await db.flush()
        self.usage_values = dict(
            subject_id=subject.subject_id,
            call_id=1,
            revision_no=1,
            input_tokens=tokens,
            completeness='unknown' if tokens is None else 'available',
            source_path='usage',
            parser_version='test',
            is_cumulative='N',
            payload_hash='a' * 64,
            raw_usage={},
            **self.audit,
        )
        db.add(HfUsageRecord(**self.usage_values))
        await db.flush()
        return job, subject

    async def calculate(self, db, job, subject, purpose='platform'):
        return await BillingCalculationService.calculate(
            db, job=job, subject_id=subject.subject_id, purpose=purpose, now=self.now, worker='test'
        )

    async def test_rounding_idempotence_and_revision_preserves_original(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db)
            event, changed = await self.calculate(db, job, subject)
            self.assertTrue(changed)
            self.assertEqual((event.amount, event.state), (Decimal('0.02'), '1'))
            self.assertEqual(await db.scalar(text('SELECT sum(amount) FROM hf_billing_line_item')), event.amount)
            revision = event.revision
            self.assertFalse((await self.calculate(db, job, subject))[1])
            self.assertEqual(event.revision, revision)
            db.add(HfUsageRecord(**(self.usage_values | dict(revision_no=2, input_tokens=1, payload_hash='b' * 64))))
            await db.flush()
            event, changed = await self.calculate(db, job, subject)
            self.assertTrue(changed)
            self.assertEqual((event.amount, event.state), (Decimal('0.02'), '3'))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_line_item')), 1)
            self.assertFalse((await self.calculate(db, job, subject))[1])

    async def test_unknown_and_missing_procurement_never_become_zero(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db, tokens=None)
            event, changed = await self.calculate(db, job, subject)
            self.assertTrue(changed)
            self.assertIsNone(event.amount)
            self.assertEqual(event.state, '0')
            self.assertEqual(await self.calculate(db, job, subject, 'procurement'), (None, False))
            job.model_variant_id = 2
            with self.assertRaises(ValueError):
                await self.calculate(db, job, subject)

    async def test_zero_is_calculated_and_outer_rollback_removes_all_facts(self):
        async with self.sessions() as db:
            job, subject = await self.seed(db, tokens=0)
            await db.commit()
            event, _ = await self.calculate(db, job, subject)
            self.assertEqual((event.amount, event.state), (Decimal('0.00'), '1'))
            await db.rollback()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_event')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_line_item')), 0)

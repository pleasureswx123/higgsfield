"""固定汇率结算、零额换算及累计调整守恒的真实数据库验证。"""
import importlib.util
import os
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from sqlalchemy import text
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod, HfBudgetReservation, HfBudgetLedgerEntry
from module_higgsfield.entity.do.exchange_rate_do import HfExchangeRateVersion
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from module_higgsfield.service.budget_settlement_service import BudgetSettlementService as Settlement
from module_higgsfield.service.billing_adjustment_service import BillingAdjustmentService
from module_higgsfield.entity.vo.billing_adjustment_vo import BillingAdjustmentInput
from tests import test_higgsfield_billing_calculation as billing


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class BudgetSettlementTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = billing.BillingCalculationTests.cleanup_schema
    migrate = billing.BillingCalculationTests.migrate
    job = billing.BillingCalculationTests.job
    seed = billing.BillingCalculationTests.seed
    calculate = billing.BillingCalculationTests.calculate

    async def asyncSetUp(self):
        await billing.BillingCalculationTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('budget_fx',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_26_exchange_rates.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def setup_budget(self, db, *, currency='CNY', fixed=True):
        job, subject = await self.seed(db)
        event, _ = await self.calculate(db, job, subject)
        job.orchestration_state = '5'
        budget = HfBudget(project_id=job.project_id, purpose='platform', currency=currency,
            cycle_kind='total', business_timezone='Asia/Shanghai', **self.audit)
        db.add(budget)
        await db.flush()
        period = HfBudgetPeriod(budget_id=budget.budget_id, period_start=self.now-timedelta(days=1),
            limit_amount=100, reserved_amount=1, consumed_amount=0, **self.audit)
        db.add(period)
        await db.flush()
        reservation = HfBudgetReservation(job_id=job.job_id, period_id=period.period_id,
            original_amount=1, remaining_amount=1, **self.audit)
        db.add(reservation)
        await db.flush()
        conversion = {}
        if fixed:
            rate = HfExchangeRateVersion(base_currency='CNY', quote_currency='USD', rate=3,
                valid_from=self.now-timedelta(days=1), valid_until=self.now+timedelta(days=1),
                source_id=1, status='1', **self.audit)
            db.add(rate)
            await db.flush()
            conversion = ExchangeRateService.convert(rate, '3', 'USD', 'CNY', at=self.now, scale=10)
            job.input_snapshot = {**job.input_snapshot, 'budgetReservations': [
                {'id': str(reservation.reservation_id), 'periodId': str(period.period_id), 'conversion': conversion}]}
        db.add(HfBudgetLedgerEntry(period_id=period.period_id, reservation_id=reservation.reservation_id,
            business_event_key=f'job:{job.job_id}:reserve', entry_type='reserve', reserved_delta=1,
            consumed_delta=0, limit_delta=0, reason='预占测试', conversion_snapshot=conversion, **self.audit))
        await db.flush()
        return job, event, period, reservation

    async def test_foreign_cumulative_rounding_refund_and_replay(self):
        async with self.sessions() as db:
            job, event, period, reservation = await self.setup_budget(db)
            event.amount = Decimal('0.0000000001')
            await db.flush()
            # 结算发生在原汇率到期后，仍使用受理时点证据。
            now = self.now + timedelta(days=10)
            await Settlement.settle(db, job.job_id, now=now, worker='test')
            self.assertEqual(period.consumed_amount, 0)
            self.assertEqual(period.reserved_amount, 0)
            self.assertEqual(reservation.state, '2')
            for index, amount in enumerate(('0.0000000001', '0.0000000001', '-0.0000000003')):
                await BillingAdjustmentService.append(db, job=job, event_id=event.event_id,
                    payload=BillingAdjustmentInput(revision=str(event.revision), deltaAmount=amount, reason='尾差及退款'),
                    business_key=f'fx:{index}', actor_id=1, now=now, actor='test')
                await Settlement.settle(db, job.job_id, now=now, worker='test')
                self.assertEqual(period.consumed_amount, Decimal('0') if index == 2 else Decimal('0.0000000001'))
                self.assertFalse(await Settlement.settle(db, job.job_id, now=now, worker='test'))
            deltas = (await db.scalars(text("SELECT consumed_delta FROM hf_budget_ledger_entry WHERE entry_type='adjust' ORDER BY entry_id"))).all()
            self.assertEqual(deltas, [Decimal('0.0000000001'), Decimal('-0.0000000001')])
            self.assertEqual(await db.scalar(text('SELECT sum(consumed_delta) FROM hf_budget_ledger_entry')), period.consumed_amount)
            self.assertEqual(event.amount, Decimal('0.0000000001'))

    async def test_missing_fixed_rate_keeps_reservation(self):
        async with self.sessions() as db:
            job, event, period, reservation = await self.setup_budget(db, fixed=False)
            await Settlement.settle(db, job.job_id, now=self.now, worker='test')
            self.assertEqual(period.consumed_amount, 0)
            self.assertEqual(period.reserved_amount, 1)
            self.assertEqual(reservation.state, '4')

    async def test_foreign_initial_and_partial_refund_use_same_evidence(self):
        async with self.sessions() as db:
            job, event, period, reservation = await self.setup_budget(db)
            await Settlement.settle(db, job.job_id, now=self.now, worker='test')
            self.assertEqual(period.consumed_amount, Decimal('0.0066666667'))
            await BillingAdjustmentService.append(db, job=job, event_id=event.event_id,
                payload=BillingAdjustmentInput(revision=str(event.revision), deltaAmount='-0.01', reason='部分退款'),
                business_key='partial-refund', actor_id=1, now=self.now, actor='test')
            await Settlement.settle(db, job.job_id, now=self.now, worker='test')
            self.assertEqual(period.consumed_amount, Decimal('0.0033333333'))
            entries = (await db.execute(text("SELECT exchange_rate_version_id,consumed_delta,conversion_snapshot FROM hf_budget_ledger_entry WHERE entry_type IN ('settle','adjust') ORDER BY entry_id"))).all()
            self.assertEqual([row[0] for row in entries], [1, 1])
            self.assertEqual(entries[1][1], Decimal('-0.0033333334'))
            self.assertEqual(entries[1][2]['sourceAdjustmentAmount'], '-0.0100000000')
            self.assertEqual(entries[1][2]['previousConvertedAmount'], '0.0066666667')
            self.assertFalse(await Settlement.settle(db, job.job_id, now=self.now, worker='test'))

    async def test_same_currency_still_settles_once(self):
        async with self.sessions() as db:
            job, event, period, reservation = await self.setup_budget(db, currency='USD', fixed=False)
            await Settlement.settle(db, job.job_id, now=self.now, worker='test')
            self.assertEqual(period.consumed_amount, event.amount)
            self.assertEqual(period.reserved_amount, 0)
            self.assertFalse(await Settlement.settle(db, job.job_id, now=self.now, worker='test'))

"""计价工作器真实事务、并发去重及失败重试。"""

import asyncio
import os
import unittest
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import text

from module_higgsfield.service.billing_worker_service import BillingWorker
from module_higgsfield.service.task_billing_read_service import TaskBillingReadService
from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.entity.do.usage_do import HfBillingSubject
from module_higgsfield.entity.do.billing_do import HfBillingEvent, HfBillingAdjustment
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod, HfBudgetReservation, HfBudgetLedgerEntry
from tests import test_higgsfield_billing_calculation as calculation


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BillingWorkerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = calculation.BillingCalculationTests.cleanup_schema
    migrate = calculation.BillingCalculationTests.migrate
    job = calculation.BillingCalculationTests.job
    seed = calculation.BillingCalculationTests.seed

    async def test_adjustment_updates_original_period_without_restoring_reservation(self):
        await self.add_reservation(Decimal('0.10'))
        worker = BillingWorker(self.sessions, 'adjustment')
        await worker.process(self.identity)
        async with self.sessions() as db:
            identity = await db.scalar(text('SELECT event_id FROM hf_billing_event'))
            db.add(
                HfBillingAdjustment(
                    event_id=identity,
                    adjustment_key='refund:1',
                    delta_amount=Decimal('-0.01'),
                    reason='已核实部分退款',
                    actor_id=1,
                    **self.audit,
                )
            )
            await db.commit()
        self.assertEqual((await worker.process(self.identity))['status'], 'handled')
        self.assertEqual((await worker.process(self.identity))['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT amount FROM hf_billing_event')), Decimal('0.02'))
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.01'))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 0)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='adjust'")), 1
            )
            self.assertEqual(
                await db.scalar(text('SELECT sum(consumed_delta) FROM hf_budget_ledger_entry')), Decimal('0.01')
            )

    async def test_invalid_refund_rolls_back_budget_adjustment(self):
        await self.add_reservation(Decimal('0.10'))
        worker = BillingWorker(self.sessions, 'invalid-refund')
        await worker.process(self.identity)
        async with self.sessions() as db:
            identity = await db.scalar(text('SELECT event_id FROM hf_billing_event'))
            db.add(
                HfBillingAdjustment(
                    event_id=identity,
                    adjustment_key='refund:bad',
                    delta_amount=Decimal('-0.03'),
                    reason='超出原费用',
                    actor_id=1,
                    **self.audit,
                )
            )
            await db.commit()
        with self.assertRaisesRegex(ValueError, '单事件有效金额'):
            await worker.process(self.identity)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.02'))
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='adjust'")), 0
            )

    async def asyncSetUp(self):
        await calculation.BillingCalculationTests.asyncSetUp(self)
        async with self.sessions() as db:
            job, _ = await self.seed(db)
            self.identity = job.job_id
            await db.commit()

    async def test_parallel_workers_and_repeated_scan_create_one_event(self):
        first, second = BillingWorker(self.sessions, 'first'), BillingWorker(self.sessions, 'second')
        results = await asyncio.gather(first.process(self.identity), second.process(self.identity))
        self.assertEqual(sorted(row['status'] for row in results), ['handled', 'skipped'])
        self.assertEqual((await first.run_once())[0]['status'], 'skipped')
        self.assertEqual((await first.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '1')
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 2)
            for table in ('hf_billing_event', 'hf_billing_line_item', 'hf_task_event', 'hf_outbox_event'):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 1)
            payload = await db.scalar(text('SELECT payload FROM hf_task_event'))
            self.assertEqual(payload, {'usageState': 'available', 'billingVisibility': 'unavailable'})

    async def test_task_billing_projection_excludes_procurement_and_hides_without_permission(self):
        worker = BillingWorker(self.sessions, 'reader')
        await worker.process(self.identity)
        async with self.sessions() as db:
            job = await BillingDao.job(db, self.identity)
            subject_id = await db.scalar(text('SELECT subject_id FROM hf_billing_subject'))
            db.add(
                HfBillingEvent(
                    subject_id=subject_id,
                    purpose='procurement',
                    price_version_id=999,
                    currency='USD',
                    amount=Decimal('987.65'),
                    state='1',
                    **self.audit,
                )
            )
            await db.flush()
            self.assertEqual(
                await TaskBillingReadService.read(db, job, {'billing:read'}), {'billingVisibility': 'hidden'}
            )
            result = await TaskBillingReadService.read(db, job, {'project:usage:read'})
            self.assertEqual(
                result['billing']['platform'], {'amount': '0.0200000000', 'currency': 'USD', 'state': 'calculated'}
            )
            self.assertEqual(result['billing']['usage']['subjects'][0]['inputTokens'], '3')
            for secret in ('987.65', 'procurement', 'rawUsage', 'priceVersionId', 'accountId'):
                self.assertNotIn(secret, str(result))

    async def test_task_projection_rejects_foreign_and_missing_usage_evidence(self):
        await BillingWorker(self.sessions, 'reader-integrity').process(self.identity)
        async with self.sessions() as db:
            job = await BillingDao.job(db, self.identity)
            event_id = await db.scalar(text("SELECT event_id FROM hf_billing_event WHERE purpose='platform'"))
            event = await BillingDao.event_by_id(db, event_id)
            usage = await BillingDao.adopted_usage(db, event.usage_record_id)
            original_subject = usage.subject_id
            usage.subject_id = original_subject + 1000
            await db.flush()
            self.assertEqual(
                await TaskBillingReadService.read(db, job, {'project:usage:read'}),
                {'billingVisibility': 'unavailable'},
            )
            usage.subject_id = original_subject
            event.usage_record_id = usage.usage_id + 1000
            await db.flush()
            self.assertEqual(
                await TaskBillingReadService.read(db, job, {'project:usage:read'}),
                {'billingVisibility': 'unavailable'},
            )
            event.usage_record_id = usage.usage_id
            await db.flush()
            recovered = await TaskBillingReadService.read(db, job, {'project:usage:read'})
            self.assertEqual(recovered['billing']['usage']['subjects'][0]['inputTokens'], '3')

    async def test_notification_failure_rolls_back_and_next_scan_recovers(self):
        worker = BillingWorker(self.sessions, 'recovery')
        with patch(
            'module_higgsfield.service.billing_worker_service.JobEventDao.usage', side_effect=RuntimeError('test')
        ):
            self.assertEqual((await worker.run_once())[0]['status'], 'failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_event')), 0)
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')

    async def add_reservation(self, amount, *, currency='USD'):
        async with self.sessions() as db:
            budget = HfBudget(
                project_id=1,
                purpose='platform',
                currency=currency,
                cycle_kind='monthly',
                business_timezone='Asia/Shanghai',
                active='N',
                **self.audit,
            )
            db.add(budget)
            await db.flush()
            period = HfBudgetPeriod(
                budget_id=budget.budget_id,
                period_start=datetime(2025, 1, 1, tzinfo=UTC),
                period_end=datetime(2025, 2, 1, tzinfo=UTC),
                limit_amount=amount,
                reserved_amount=amount,
                consumed_amount=0,
                **self.audit,
            )
            db.add(period)
            await db.flush()
            reservation = HfBudgetReservation(
                job_id=self.identity,
                period_id=period.period_id,
                original_amount=amount,
                remaining_amount=amount,
                **self.audit,
            )
            db.add(reservation)
            await db.flush()
            db.add(
                HfBudgetLedgerEntry(
                    period_id=period.period_id,
                    reservation_id=reservation.reservation_id,
                    business_event_key='initial',
                    entry_type='reserve',
                    reserved_delta=amount,
                    consumed_delta=0,
                    limit_delta=0,
                    reason='测试预占',
                    **self.audit,
                )
            )
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5', upstream_state='3'"))
            await db.commit()

    async def test_original_disabled_period_settles_and_releases_remainder_atomically(self):
        await self.add_reservation(Decimal('0.03'))
        worker = BillingWorker(self.sessions, 'settler')
        with patch(
            'module_higgsfield.service.billing_worker_service.JobEventDao.usage', side_effect=RuntimeError('test')
        ):
            self.assertEqual((await worker.run_once())[0]['status'], 'failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), Decimal('0.03'))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 1)
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual((await worker.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.02'))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_budget_reservation')), '2')
            rows = (
                await db.execute(
                    text(
                        'SELECT entry_type,reserved_delta,consumed_delta FROM hf_budget_ledger_entry ORDER BY entry_id'
                    )
                )
            ).all()
            self.assertEqual(
                rows[-2:], [('settle', Decimal('-0.02'), Decimal('0.02')), ('release', Decimal('-0.01'), Decimal('0'))]
            )
            self.assertEqual(sum(row[1] for row in rows), 0)

    async def test_actual_cost_can_exceed_original_reservation(self):
        await self.add_reservation(Decimal('0.01'))
        worker = BillingWorker(self.sessions, 'overrun')
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.02'))
            self.assertEqual(await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), 0)
            self.assertEqual(
                await db.scalar(text('SELECT limit_amount-reserved_amount-consumed_amount FROM hf_budget_period')),
                Decimal('-0.01'),
            )

    async def test_cross_currency_does_not_release_or_assume_exchange_rate(self):
        await self.add_reservation(Decimal('0.03'), currency='CNY')
        worker = BillingWorker(self.sessions, 'currency')
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual((await worker.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), Decimal('0.03')
            )
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_budget_reservation')), '4')
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), 0)

    async def test_unknown_registration_retains_reserve_until_its_fee_arrives(self):
        await self.add_reservation(Decimal('0.10'))
        async with self.sessions() as db:
            subject = HfBillingSubject(
                account_id=1,
                job_id=self.identity,
                origin_call_id=2,
                subject_kind='registration',
                identity_key='call:2',
                **self.audit,
            )
            db.add(subject)
            await db.flush()
            extra_id = subject.subject_id
            await db.commit()
        worker = BillingWorker(self.sessions, 'multiple')
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual((await worker.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')
            self.assertEqual(
                await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), Decimal('0.08')
            )
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.02'))
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='release'")), 0
            )
            db.add(
                HfBillingEvent(
                    subject_id=extra_id,
                    purpose='platform',
                    price_version_id=1,
                    currency='USD',
                    amount=Decimal('0.03'),
                    state='1',
                    **self.audit,
                )
            )
            await db.commit()
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual((await worker.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), 0)
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), Decimal('0.05'))
            self.assertEqual(
                await db.scalar(text("SELECT reserved_delta FROM hf_budget_ledger_entry WHERE entry_type='release'")),
                Decimal('-0.05'),
            )

    async def test_wrong_budget_owner_rolls_back_pricing_and_settlement(self):
        await self.add_reservation(Decimal('0.10'))
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_budget SET project_id=999'))
            await db.commit()
        worker = BillingWorker(self.sessions, 'ownership')
        self.assertEqual((await worker.run_once())[0]['status'], 'failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_event')), 0)
            self.assertEqual(
                await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), Decimal('0.10')
            )

    async def test_verified_zero_releases_reservation_without_zero_ledger(self):
        await self.add_reservation(Decimal('0.10'))
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_usage_record SET input_tokens=0'))
            await db.commit()
        worker = BillingWorker(self.sessions, 'free')
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual((await worker.run_once())[0]['status'], 'skipped')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT amount FROM hf_billing_event')), 0)
            self.assertEqual(await db.scalar(text('SELECT consumed_amount FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT remaining_amount FROM hf_budget_reservation')), 0)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='settle'")), 0
            )

"""内部预占服务的多约束原子性，不代表生成任务接口已接通。"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.budget_vo import BudgetCreate
from module_higgsfield.entity.vo.budget_period_vo import BudgetPeriodCreate
from module_higgsfield.service.budget_service import BudgetService
from module_higgsfield.service.budget_period_service import BudgetPeriodService
from module_higgsfield.service.budget_reservation_service import BudgetReservationService
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from module_higgsfield.entity.do.budget_do import HfBudgetLedgerEntry
from tests import test_higgsfield_budget_periods as periods


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetReservationTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = periods.BudgetPeriodTests.cleanup_schema
    create = periods.BudgetPeriodTests.create
    payload = periods.BudgetPeriodTests.payload
    save_budget = periods.BudgetPeriodTests.save_budget
    period = periods.BudgetPeriodTests.period
    save_period = periods.BudgetPeriodTests.save_period

    async def asyncSetUp(self):
        await periods.BudgetPeriodTests.asyncSetUp(self)
        await self.save_period(self.period())
        async with self.sessions() as db:
            budget, _ = await BudgetService.save(
                db,
                self.owner,
                BudgetCreate(
                    subject={'projectId': str(self.project_id)},
                    purpose='platform',
                    currency='CNY',
                    cycleKind='total',
                    businessTimezone='Asia/Shanghai',
                ),
                str(uuid4()),
            )
            await BudgetPeriodService.save(
                db,
                self.owner,
                budget['data']['id'],
                BudgetPeriodCreate(periodStart='2026-01-01T00:00:00Z', limitAmount='100', reason='项目总额'),
                str(uuid4()),
            )
        self.at = datetime(2027, 1, 15, tzinfo=timezone.utc)

    async def reserve(self, job, amount='60', **changes):
        async with self.sessions() as db:
            try:
                result = await BudgetReservationService.reserve(
                    db,
                    self.owner,
                    **(
                        dict(
                            job_id=job,
                            project_id=self.project_id,
                            at=self.at,
                            estimates={('platform', 'CNY'): amount},
                            missing_budget_policy='reject',
                        )
                        | changes
                    ),
                )
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

    async def test_concurrent_jobs_obey_all_budgets(self):
        outcomes = await asyncio.gather(self.reserve(101), self.reserve(102), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in outcomes), 1)
        result = next(value for value in outcomes if isinstance(value, list))
        self.assertEqual(len(result), 2)
        async with self.sessions() as db:
            balances = (
                (await db.execute(text('SELECT reserved_amount FROM hf_budget_period ORDER BY period_id')))
                .scalars()
                .all()
            )
            self.assertEqual(balances, [Decimal('60'), Decimal('60')])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_reservation')), 2)
            winner = await db.scalar(text('SELECT job_id FROM hf_budget_reservation LIMIT 1'))
        with self.assertRaises(ServiceWarning):
            await self.reserve(winner)

    async def test_foreign_currency_freezes_rate_and_rounds_up(self):
        async with self.sessions() as db:
            await db.execute(text("""INSERT INTO hf_exchange_rate_version
                (base_currency,quote_currency,rate,valid_from,source_id,status,create_time,update_time)
                VALUES ('CNY','USD',3,'2026-01-01T00:00:00Z',1,'1',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""))
            await db.commit()
        result = await self.reserve(201, estimates={('platform', 'USD'): '1'})
        self.assertEqual(len(result), 2)
        for reservation in result:
            self.assertEqual(reservation['originalAmount'], '0.3333333334')
            self.assertEqual(reservation['conversion']['direction'], 'divide')
            self.assertEqual(reservation['conversion']['roundingMode'], 'ceiling')
            self.assertEqual(reservation['conversion']['exchangeRateVersionId'], '1')
        async with self.sessions() as db:
            snapshots = (await db.scalars(text("SELECT conversion_snapshot FROM hf_budget_ledger_entry WHERE entry_type='reserve'"))).all()
            self.assertEqual(len(snapshots), 2)
            self.assertEqual(snapshots[0]['sourceAmount'], '1')
        # 零额也返回完整汇率快照，由任务受理事务保存，不写零变动账本。
        zero = await self.reserve(202, estimates={('platform', 'USD'): '0'})
        self.assertEqual(zero[0]['conversion']['exchangeRateVersionId'], '1')
        self.assertEqual(zero[0]['originalAmount'], '0.0000000000')

    async def test_missing_foreign_rate_refuses_without_partial_reservation(self):
        with self.assertRaises(ServiceWarning) as caught:
            await self.reserve(203, estimates={('platform', 'USD'): '1'})
        self.assertEqual(caught.exception.data['errorCode'], 'BUDGET_EXCHANGE_RATE_REQUIRED')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_reservation')), 0)

    async def test_one_insufficient_period_has_no_partial_reservation(self):
        async with self.sessions() as db:
            # 仅设置第二个约束用于预占拒绝测试，不模拟调额接口。
            await db.execute(
                text(
                    'UPDATE hf_budget_period SET limit_amount=10 WHERE period_id=(SELECT max(period_id) FROM hf_budget_period)'
                )
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.reserve(101)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT sum(reserved_amount) FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_reservation')), 0)

    async def test_failure_after_first_ledger_rolls_back_savepoint(self):
        original = BudgetReservationDao.add
        count = 0

        async def fail_second(db, model, **values):
            nonlocal count
            if model is HfBudgetLedgerEntry:
                count += 1
                if count == 2:
                    raise RuntimeError('模拟第二预算账本失败')
            return await original(db, model, **values)

        async with self.sessions() as db:
            with patch.object(BudgetReservationDao, 'add', side_effect=fail_second), self.assertRaises(RuntimeError):
                await BudgetReservationService.reserve(
                    db,
                    self.owner,
                    job_id=101,
                    project_id=self.project_id,
                    at=self.at,
                    estimates={('platform', 'CNY'): '10'},
                    missing_budget_policy='reject',
                )
            # 即使外层捕获异常并提交，保存点也不能留下部分预占。
            await db.commit()
            self.assertEqual(await db.scalar(text('SELECT sum(reserved_amount) FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_reservation')), 0)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='reserve'")), 0
            )

    async def test_unknown_estimate_missing_period_and_known_zero(self):
        with self.assertRaises(ServiceWarning):
            await self.reserve(101, estimates={})
        with self.assertRaises(ServiceWarning):
            await self.reserve(101, at=datetime(2028, 1, 1, tzinfo=timezone.utc))
        result = await self.reserve(101, '0')
        self.assertEqual(len(result), 2)
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='reserve'")), 0
            )

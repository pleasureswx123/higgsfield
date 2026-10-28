"""周期边界、降额与账本同事务守恒验证。"""

import asyncio
from decimal import Decimal
import os
import unittest
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.budget_period_vo import BudgetPeriodCreate, BudgetLimitUpdate, BudgetPeriodQuery
from module_higgsfield.service.budget_period_service import BudgetPeriodService
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from tests import test_higgsfield_budgets as budgets


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetPeriodTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = budgets.BudgetTests.cleanup_schema
    create = budgets.BudgetTests.create
    payload = budgets.BudgetTests.payload
    save_budget = budgets.BudgetTests.save_budget

    async def asyncSetUp(self):
        await budgets.BudgetTests.asyncSetUp(self)
        result, _ = await self.save_budget(self.payload())
        self.budget_id = result['data']['id']

    def period(self, **changes):
        return BudgetPeriodCreate(
            **(
                dict(
                    periodStart='2027-01-01T00:00:00+08:00',
                    periodEnd='2027-02-01T00:00:00+08:00',
                    limitAmount='100',
                    reason='月度额度',
                )
                | changes
            )
        )

    async def save_period(self, payload, key=None, identity=None, adjust=False):
        async with self.sessions() as db:
            return await BudgetPeriodService.save(
                db, self.owner, identity or self.budget_id, payload, key or str(uuid4()), adjust=adjust
            )

    async def test_initialization_replay_lower_limit_and_ledger_sum(self):
        key = str(uuid4())
        initial, _ = await self.save_period(self.period(), key)
        repeated, replay = await self.save_period(self.period(), key)
        self.assertTrue(replay)
        self.assertEqual(initial, repeated)
        identity = initial['data']['id']
        async with self.sessions() as db:
            # 模拟已有消费/预占；本测试只验证调额不篡改该两项。
            await db.execute(
                text('UPDATE hf_budget_period SET consumed_amount=60,reserved_amount=20 WHERE period_id=:id'),
                {'id': int(identity)},
            )
            await db.commit()
        changed, _ = await self.save_period(
            BudgetLimitUpdate(revision='1', newLimit='50', reason='降低额度'), identity=identity, adjust=True
        )
        self.assertEqual(changed['data']['availableAmount'], '-30.0000000000')
        self.assertEqual(changed['data']['consumedAmount'], '60.0000000000')
        self.assertEqual(changed['data']['reservedAmount'], '20.0000000000')
        async with self.sessions() as db:
            total = await db.scalar(
                text('SELECT sum(limit_delta) FROM hf_budget_ledger_entry WHERE period_id=:id'), {'id': int(identity)}
            )
            self.assertEqual(total, Decimal('50'))
            page = await BudgetPeriodService.listing(db, self.owner, identity, BudgetPeriodQuery(), ledger=True)
            self.assertEqual(page.total, 2)
            self.assertEqual(page.rows[0]['limitDelta'], '-50.0000000000')
        with self.assertRaises(ServiceWarning):
            await self.save_period(
                BudgetLimitUpdate(revision='1', newLimit='70', reason='旧版本'), identity=identity, adjust=True
            )

    async def test_month_bounds_overlap_and_zero_initialization(self):
        for changes in (
            {'periodStart': '2027-01-01T00:00:00Z'},
            {'periodEnd': '2027-03-01T00:00:00+08:00'},
            {'periodEnd': None},
        ):
            with self.assertRaises(ServiceWarning):
                await self.save_period(self.period(**changes))
        results = await asyncio.gather(
            self.save_period(self.period(limitAmount='0')),
            self.save_period(self.period(limitAmount='0')),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in results), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_period')), 1)
        await self.save_period(
            self.period(periodStart='2027-02-01T00:00:00+08:00', periodEnd='2027-03-01T00:00:00+08:00')
        )

    async def test_adjustment_failure_rolls_back_balance_and_ledger(self):
        initial, _ = await self.save_period(self.period())
        identity = initial['data']['id']
        with (
            patch.object(PriceSourceDao, 'audit', new=AsyncMock(side_effect=RuntimeError('模拟审计失败'))),
            self.assertRaises(RuntimeError),
        ):
            await self.save_period(
                BudgetLimitUpdate(revision='1', newLimit='20', reason='测试回滚'), identity=identity, adjust=True
            )
        async with self.sessions() as db:
            page = await BudgetPeriodService.listing(db, self.owner, self.budget_id, BudgetPeriodQuery())
            self.assertEqual(page.rows[0]['limitAmount'], '100.0000000000')
            self.assertEqual(page.rows[0]['revision'], '1')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 1)

    async def test_total_period_and_unchanged_limit(self):
        budget, _ = await self.save_budget(self.payload(cycleKind='total'))
        identity = budget['data']['id']
        with self.assertRaises(ServiceWarning):
            await self.save_period(self.period(), identity=identity)
        created, _ = await self.save_period(self.period(periodEnd=None), identity=identity)
        period_id = created['data']['id']
        await self.save_period(
            BudgetLimitUpdate(revision='1', newLimit='100', reason='确认额度不变'), identity=period_id, adjust=True
        )
        with self.assertRaises(ServiceWarning):
            await self.save_period(self.period(periodStart='2028-01-01T00:00:00Z', periodEnd=None), identity=identity)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 1)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_budget_period')), 2)

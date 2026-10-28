"""预算状态的金额隐藏、采购隔离和缺周期阻断。"""

import os
import unittest
from datetime import datetime, UTC
from decimal import Decimal
from sqlalchemy import text
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod
from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.budget_status_service import BudgetStatusService
from tests import test_higgsfield_billing_admin as admin


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetStatusTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = admin.BillingAdminTests.cleanup_schema
    migrate = admin.BillingAdminTests.migrate
    job = admin.BillingAdminTests.job
    seed = admin.BillingAdminTests.seed
    create = admin.BillingAdminTests.create
    asyncSetUp = admin.BillingAdminTests.asyncSetUp

    def policy(self, missing='reject'):
        return GenerationPolicy(platformCurrency='CNY', procurementCurrency='USD', missingBudgetPolicy=missing)

    async def grant(self, db, permission):
        await db.execute(
            text(
                "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"
            ),
            {'permission': permission},
        )

    async def test_no_budget_policy_and_missing_period_do_not_create_records(self):
        async with self.sessions() as db:
            await self.grant(db, 'generation:create')
            await db.commit()
            denied = await BudgetStatusService.status(db, self.owner, 1, self.policy())
            self.assertEqual(denied['blockingCodes'], ['BUDGET_REQUIRED'])
            self.assertNotIn('periods', denied)
            self.assertTrue((await BudgetStatusService.status(db, self.owner, 1, self.policy('allow')))['canSubmit'])
            db.add(
                HfBudget(
                    project_id=1,
                    purpose='platform',
                    currency='CNY',
                    cycle_kind='total',
                    business_timezone='Asia/Shanghai',
                    **self.audit,
                )
            )
            await db.flush()
            result = await BudgetStatusService.status(db, self.owner, 1, self.policy('allow'))
            self.assertEqual(result['blockingCodes'], ['BUDGET_PERIOD_REQUIRED'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_reservation')), 0)

    async def test_only_platform_amounts_visible_but_procurement_shortfall_blocks(self):
        async with self.sessions() as db:
            await self.grant(db, 'generation:create')
            for purpose, currency, limit, consumed in [
                ('platform', 'CNY', '100', '10'),
                ('procurement', 'USD', '999', '1000'),
            ]:
                budget = HfBudget(
                    project_id=1,
                    purpose=purpose,
                    currency=currency,
                    cycle_kind='total',
                    business_timezone='Asia/Shanghai',
                    **self.audit,
                )
                db.add(budget)
                await db.flush()
                db.add(
                    HfBudgetPeriod(
                        budget_id=budget.budget_id,
                        period_start=datetime(2020, 1, 1, tzinfo=UTC),
                        limit_amount=Decimal(limit),
                        consumed_amount=Decimal(consumed),
                        reserved_amount=0,
                        **self.audit,
                    )
                )
            await db.commit()
            result = await BudgetStatusService.status(db, self.owner, 1, self.policy())
            self.assertEqual(result['amountVisibility'], 'hidden')
            self.assertNotIn('periods', result)
            self.assertEqual(result['blockingCodes'], ['BUDGET_INSUFFICIENT'])
            await self.grant(db, 'project:usage:read')
            await db.commit()
            result = await BudgetStatusService.status(db, self.owner, 1, self.policy())
            self.assertEqual(len(result['periods']), 1)
            self.assertEqual(result['periods'][0]['availableAmount'], '90.0000000000')
            self.assertNotIn('999', str(result))
            self.assertFalse(result['canSubmit'])
            await db.execute(
                text(
                    "UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='project:usage:read'"
                )
            )
            await db.commit()
            own = await BudgetStatusService.status(db, self.owner, 1, self.policy())
            self.assertEqual(own['periods'], [])
            self.assertEqual(own['blockingCodes'], ['BUDGET_INSUFFICIENT'])

"""预算存储约束与真实迁移验证，不代表受理结算流程已接通。"""

from decimal import Decimal
import importlib.util
import os
from pathlib import Path
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod, HfBudgetReservation, HfBudgetLedgerEntry
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'budget_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_27_budgets.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def migrate(self, operation):
        async with self.engine.begin() as conn:

            def execute(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    getattr(self.migration, operation)()

            await conn.run_sync(execute)

    def budget(self, **changes):
        return HfBudget(
            **(
                dict(
                    user_id=1,
                    purpose='platform',
                    currency='CNY',
                    cycle_kind='total',
                    business_timezone='Asia/Shanghai',
                    **WriteService.audit(self.owner),
                )
                | changes
            )
        )

    def ledger(self, key, kind, reserved='0', consumed='0', limit='0', **changes):
        return HfBudgetLedgerEntry(
            **(
                dict(
                    period_id=1,
                    business_event_key=key,
                    entry_type=kind,
                    reserved_delta=Decimal(reserved),
                    consumed_delta=Decimal(consumed),
                    limit_delta=Decimal(limit),
                    reason='测试变动',
                    **WriteService.audit(self.owner),
                )
                | changes
            )
        )

    async def test_subject_uniqueness_and_excess_balance_allowed(self):
        async with self.sessions() as db:
            db.add(self.budget())
            await db.flush()
            for values in ({}, {'project_id': 1}, {'user_id': None}):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(self.budget(**values))
                        await db.flush()
            period = HfBudgetPeriod(
                budget_id=1,
                period_start=WriteService.audit(self.owner)['create_time'],
                limit_amount=Decimal('10'),
                reserved_amount=Decimal('20'),
                consumed_amount=Decimal('30'),
                **WriteService.audit(self.owner),
            )
            db.add(period)
            await db.flush()
            self.assertEqual(period.limit_amount - period.reserved_amount - period.consumed_amount, Decimal('-40'))
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        HfBudgetReservation(
                            job_id=1,
                            period_id=period.period_id,
                            original_amount=Decimal('10'),
                            remaining_amount=Decimal('11'),
                            **WriteService.audit(self.owner),
                        )
                    )
                    await db.flush()

    async def test_ledger_directions_evidence_and_business_key(self):
        async with self.sessions() as db:
            entries = [
                self.ledger('initial', 'change_limit', limit='100'),
                self.ledger('reserve', 'reserve', reserved='15', reservation_id=1),
                self.ledger(
                    'settle', 'settle', reserved='-12.393', consumed='12.393', billing_event_id=1, reservation_id=1
                ),
                self.ledger('release', 'release', reserved='-2.607', reservation_id=1),
            ]
            db.add_all(entries)
            await db.flush()
            totals = (
                await db.execute(
                    text('SELECT sum(reserved_delta),sum(consumed_delta),sum(limit_delta) FROM hf_budget_ledger_entry')
                )
            ).one()
            self.assertEqual(totals, (Decimal('0'), Decimal('12.393'), Decimal('100')))
            invalid = [
                self.ledger('zero', 'change_limit'),
                self.ledger('wrong', 'reserve', reserved='-1', reservation_id=1),
                self.ledger('missing', 'settle', consumed='1'),
                self.ledger('adjust', 'adjust', consumed='-1'),
                self.ledger('initial', 'change_limit', limit='2'),
            ]
            for entry in invalid:
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(entry)
                        await db.flush()

    async def test_comments_no_foreign_keys_and_migration_roundtrip(self):
        async with self.sessions() as db:
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_budget','hf_budget_period','hf_budget_reservation','hf_budget_ledger_entry') AND a.attnum>0 AND NOT a.attisdropped AND col_description(c.oid,a.attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            foreign = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_budget','hf_budget_period','hf_budget_reservation','hf_budget_ledger_entry') AND x.contype='f'"
                )
            )
            self.assertEqual(foreign, 0)
        await self.migrate('downgrade')
        await self.migrate('upgrade')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 0)

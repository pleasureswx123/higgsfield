"""原周期预占释放的守恒、去重与失败原子性。"""

import asyncio
import importlib.util
import os
from pathlib import Path
from decimal import Decimal
import unittest
from unittest.mock import patch
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.budget_release_service import BudgetReleaseService
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from tests import test_higgsfield_budget_reservations as reservations
from tests import test_higgsfield_job_storage as jobs


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetReleaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reservations.BudgetReservationTests.cleanup_schema
    create = reservations.BudgetReservationTests.create
    payload = reservations.BudgetReservationTests.payload
    save_budget = reservations.BudgetReservationTests.save_budget
    period = reservations.BudgetReservationTests.period
    save_period = reservations.BudgetReservationTests.save_period
    reserve = reservations.BudgetReservationTests.reserve
    job = jobs.JobStorageTests.job

    async def asyncSetUp(self):
        await reservations.BudgetReservationTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'release_jobs', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_29_jobs_outbox.py'
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:

            def upgrade(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    migration.upgrade()

            await conn.run_sync(upgrade)
        async with self.sessions() as db:
            db.add(
                self.job(
                    job_id=101,
                    project_id=self.project_id,
                    orchestration_state='5',
                    upstream_state='0',
                    cancel_state='2',
                )
            )
            await db.commit()
        await self.reserve(101)

    async def release(self):
        async with self.sessions() as db:
            db.autoflush = False
            result = await BudgetReleaseService.release_unsubmitted(db, self.owner, 101, reason='上游未提交的本地取消')
            await db.commit()
            return result

    async def test_concurrent_release_once_and_original_period_conservation(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_budget SET active='N'"))
            await db.commit()
        results = await asyncio.gather(self.release(), self.release())
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0]), 2)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT sum(reserved_amount) FROM hf_budget_period')), Decimal(0))
            self.assertEqual(await db.scalar(text('SELECT sum(consumed_amount) FROM hf_budget_period')), Decimal(0))
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='release'")), 2
            )
            self.assertEqual(
                await db.scalar(text('SELECT sum(reserved_delta) FROM hf_budget_ledger_entry')), Decimal(0)
            )
            self.assertEqual(
                await db.scalar(
                    text("SELECT count(*) FROM hf_budget_reservation WHERE state='3' AND remaining_amount=0")
                ),
                2,
            )

    async def test_unknown_and_upstream_cancel_do_not_release(self):
        async with self.sessions() as db:
            for state in ('6', '5', '4'):
                await db.execute(text('UPDATE hf_creation_job SET upstream_state=:state'), {'state': state})
                await db.commit()
                with self.assertRaises(ServiceWarning):
                    await BudgetReleaseService.release_unsubmitted(db, self.owner, 101, reason='不可据此认定免费')
            self.assertEqual(await db.scalar(text('SELECT sum(reserved_amount) FROM hf_budget_period')), Decimal('120'))
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='release'")), 0
            )

    async def test_second_ledger_failure_rolls_back_all_even_if_outer_commits(self):
        original = BudgetReservationDao.add
        count = 0

        async def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('模拟第二周期账本故障')
            return await original(*args, **kwargs)

        async with self.sessions() as db:
            db.autoflush = False
            with patch.object(BudgetReservationDao, 'add', side_effect=fail_second), self.assertRaises(RuntimeError):
                await BudgetReleaseService.release_unsubmitted(db, self.owner, 101, reason='本地取消')
            await db.commit()
            self.assertEqual(await db.scalar(text('SELECT sum(reserved_amount) FROM hf_budget_period')), Decimal('120'))
            self.assertEqual(
                await db.scalar(text('SELECT sum(remaining_amount) FROM hf_budget_reservation')), Decimal('120')
            )
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='release'")), 0
            )

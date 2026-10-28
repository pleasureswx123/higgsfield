"""本地取消、预算释放与任务事件的整体事务验证。"""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.generation_cancel_service import GenerationCancelService
from module_higgsfield.entity.vo.generation_action_vo import GenerationCancel
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.controller.project_workspace_controller import mutation_response
from tests import test_higgsfield_generation_snapshot as snapshots
from pydantic import ValidationError
from module_higgsfield.service.generation_read_service import GenerationReadService


class GenerationCancelInputTests(unittest.TestCase):
    def test_reason_rejects_whitespace(self):
        with self.assertRaises(ValidationError):
            GenerationCancel(revision='8', reason='   ')
        self.assertEqual(GenerationCancel(revision='8', reason=' 原因 ').reason, '原因')


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationCancelTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = snapshots.GenerationSnapshotTests.cleanup_schema
    migrate = snapshots.GenerationSnapshotTests.migrate
    job = snapshots.GenerationSnapshotTests.job
    output = snapshots.GenerationSnapshotTests.output
    create = snapshots.GenerationSnapshotTests.create

    async def asyncSetUp(self):
        await snapshots.GenerationSnapshotTests.asyncSetUp(self)
        for name in ('20261027_27_budgets.py', '20261027_34_generation_cancel_permission.py'):
            spec = importlib.util.spec_from_file_location(
                'cancel_setup', Path(__file__).resolve().parents[1] / 'alembic/versions' / name
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET orchestration_state='1',upstream_state='0',lease_owner='worker',lease_until=clock_timestamp()+interval '1 minute',fencing_token=3"
                )
            )
            await db.execute(text('DELETE FROM hf_generated_output'))
            await db.execute(
                text(
                    "INSERT INTO hf_budget_period(budget_id,period_start,limit_amount,reserved_amount,create_time,update_time) VALUES(1,'2026-01-01T00:00:00Z',100,60,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            await db.execute(
                text(
                    'INSERT INTO hf_budget_reservation(job_id,period_id,original_amount,remaining_amount,create_time,update_time) VALUES(:job,1,60,60,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)'
                ),
                {'job': self.job_id},
            )
            await db.commit()

    async def cancel(self, key=None):
        async with self.sessions() as db:
            db.autoflush = False
            return await GenerationCancelService.cancel(
                db,
                self.owner,
                self.job_id,
                GenerationCancel(revision='8', reason='停止未提交任务'),
                key or str(uuid4()),
            )

    async def test_cancel_replay_releases_once_and_invalidates_worker(self):
        async with self.sessions() as db:
            before = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertIn('generation:cancel', before['allowedActions'])
            self.assertNotIn('generation:copy-input', before['allowedActions'])
            await db.execute(text(
                "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) "
                "SELECT role_id,'generation:create','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP "
                "FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"
            ))
            await db.commit()
            permitted = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertIn('generation:copy-input', permitted['allowedActions'])
        key = str(uuid4())
        original = await self.cancel(key)
        repeated = await self.cancel(key)
        self.assertTrue(repeated[1])
        self.assertNotIn('generation:cancel', repeated[0]['data']['task']['allowedActions'])
        self.assertEqual(original[0]['data']['task']['cancelState'], 'confirmed')
        self.assertEqual(mutation_response(original).status_code, 200)
        async with self.sessions() as db:
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_state,cancel_state,lease_owner,fencing_token FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(row, ('5', '0', '2', None, 4))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 0)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_budget_ledger_entry WHERE entry_type='release'")), 1
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.cancel(key)

    async def test_submitting_unknown_and_running_are_not_local_cancellation(self):
        for state in ('2', '3', '4'):
            async with self.sessions() as db:
                await db.execute(text('UPDATE hf_creation_job SET orchestration_state=:state'), {'state': state})
                await db.commit()
            with self.assertRaises(ServiceWarning):
                await self.cancel()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 60)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)

    async def test_audit_failure_rolls_back_cancellation_release_and_event(self):
        with (
            patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('模拟审计故障'))),
            self.assertRaises(RuntimeError),
        ):
            await self.cancel()
        async with self.sessions() as db:
            self.assertEqual(
                (
                    await db.execute(
                        text('SELECT orchestration_state,cancel_state,revision,lease_owner FROM hf_creation_job')
                    )
                ).one(),
                ('1', '0', 8, 'worker'),
            )
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 60)
            for table in ('hf_task_event', 'hf_outbox_event', 'hf_budget_ledger_entry'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM ' + table)), 0)

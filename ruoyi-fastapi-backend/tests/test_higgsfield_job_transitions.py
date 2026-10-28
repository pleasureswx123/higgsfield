"""任务状态推进、事件原子性和旧执行者隔离。"""

import os
import unittest
from typing import NoReturn
from unittest.mock import patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.job_lease_service import JobLease
from module_higgsfield.service.job_transition_service import JobTransitionService
from tests import test_higgsfield_job_leases as leases


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class JobTransitionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = leases.JobLeaseTests.cleanup_schema
    migrate = leases.JobLeaseTests.migrate
    job = leases.JobLeaseTests.job
    asyncSetUp = leases.JobLeaseTests.asyncSetUp
    seed = leases.JobLeaseTests.seed
    claim = leases.JobLeaseTests.claim

    async def advance(self, lease: JobLease, action: str, **kwargs) -> JobLease:
        async with self.sessions() as db:
            db.autoflush = False
            return await JobTransitionService.apply(db, lease, action=action, retry_after_seconds=0, **kwargs)

    async def test_failed_lifecycle_preserves_billing_and_snapshot(self) -> None:
        await self.seed(billing_state='3')
        original = (await self.claim('worker'))[0]
        lease = await self.advance(original, 'prepare')
        lease = await self.advance(lease, 'submit')
        await self.advance(lease, 'accepted', upstream_task_id='provider-job-1')
        lease = (await self.claim('poller'))[0]
        await self.advance(lease, 'running')
        lease = (await self.claim('poller'))[0]
        await self.advance(lease, 'running')
        lease = (await self.claim('poller'))[0]
        with self.assertRaises(ValueError):
            await self.advance(lease, 'succeeded')
        await self.advance(lease, 'failed')
        async with self.sessions() as db:
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_state,billing_state,revision,event_sequence,upstream_task_id,input_snapshot,finished_time,lease_owner,next_action_time FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(row[:6], ('5', '4', '3', 6, 5, 'provider-job-1'))
            self.assertEqual(row[6], {'schemaVersion': 1})
            self.assertIsNotNone(row[7])
            self.assertIsNone(row[8])
            self.assertIsNone(row[9])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 5)
            payload = await db.scalar(text('SELECT payload FROM hf_task_event ORDER BY sequence DESC LIMIT 1'))
            self.assertEqual(payload['orchestrationState'], 'finished')
            self.assertEqual(payload['upstreamState'], 'failed')
        with self.assertRaises(ServiceWarning):
            await self.advance(original, 'prepare')

    async def test_unknown_cannot_resubmit_or_be_treated_as_rejected(self) -> None:
        await self.seed(orchestration_state='2')
        # 领取丢失提交租约本身转入未知阶段。
        lease = (await self.claim('reconcile'))[0]
        for action in ('submit', 'rejected', 'failed'):
            with self.assertRaises(ServiceWarning):
                await self.advance(lease, action)
        with self.assertRaises(ServiceWarning):
            await self.advance(lease, 'accepted')
        await self.advance(lease, 'accepted', upstream_task_id='confirmed-task')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT upstream_task_id FROM hf_creation_job')), 'confirmed-task')

    async def test_event_failure_rolls_back_state_and_outbox(self) -> None:
        await self.seed()
        lease = (await self.claim('worker'))[0]
        original = JobEventDao.state

        async def fail_after_flush(*args) -> NoReturn:
            await original(*args)
            raise RuntimeError('模拟提交前故障')

        with patch.object(JobEventDao, 'state', side_effect=fail_after_flush), self.assertRaises(RuntimeError):
            await self.advance(lease, 'prepare')
        async with self.sessions() as db:
            row = (
                await db.execute(text('SELECT orchestration_state,revision,event_sequence FROM hf_creation_job'))
            ).one()
            self.assertEqual(row, ('0', 1, 0))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 0)
        await self.advance(lease, 'prepare')

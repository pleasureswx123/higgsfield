"""任务租约并发、栅栏与提交未知恢复测试。"""

import asyncio
import importlib.util
from pathlib import Path
import os
import unittest
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.job_lease_service import JobLeaseService
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class JobLeaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate
    job = storage.JobStorageTests.job

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'lease_calls', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_35_provider_calls.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def seed(self, **changes):
        async with self.sessions() as db:
            row = self.job(**changes)
            db.add(row)
            await db.flush()
            identity = row.job_id
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second' WHERE job_id=:id"
                ),
                {'id': identity},
            )
            await db.commit()
            return identity

    async def claim(self, worker):
        async with self.sessions() as db:
            return await JobLeaseService.claim(db, worker, limit=1)

    async def test_concurrent_claim_is_exclusive_and_renew_is_invisible(self):
        identity = await self.seed()
        results = await asyncio.gather(self.claim('worker-a'), self.claim('worker-b'))
        leases = [lease for batch in results for lease in batch]
        self.assertEqual(len(leases), 1)
        lease = leases[0]
        self.assertEqual(lease.job_id, identity)
        self.assertEqual(lease.action, 'prepare')
        async with self.sessions() as db:
            await JobLeaseService.renew(db, lease)
            row = (await db.execute(text('SELECT revision,event_sequence,fencing_token FROM hf_creation_job'))).one()
            self.assertEqual(row, (1, 0, 1))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)
            await JobLeaseService.release(db, lease, retry_after_seconds=0)
        newer = (await self.claim('worker-c'))[0]
        self.assertEqual(newer.fencing_token, 2)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await JobLeaseService.renew(db, lease)

    async def test_expired_submission_becomes_unknown_with_event(self):
        identity = await self.seed(orchestration_state='2')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET lease_owner='lost-worker',lease_until=clock_timestamp()-interval '1 second',fencing_token=5 WHERE job_id=:id"
                ),
                {'id': identity},
            )
            await db.commit()
        lease = (await self.claim('recovery-worker'))[0]
        self.assertEqual((lease.action, lease.fencing_token, lease.revision), ('reconcile_submission', 6, 2))
        async with self.sessions() as db:
            row = (
                await db.execute(text('SELECT orchestration_state,upstream_state,event_sequence FROM hf_creation_job'))
            ).one()
            self.assertEqual(row, ('3', '6', 1))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 1)
            await JobLeaseService.release(db, lease, retry_after_seconds=0)
        lease = (await self.claim('another-recovery'))[0]
        self.assertEqual(lease.action, 'reconcile_submission')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)

    async def test_expired_or_revision_changed_worker_cannot_write(self):
        identity = await self.seed()
        lease = (await self.claim('worker'))[0]
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_creation_job SET revision=revision+1 WHERE job_id=:id'), {'id': identity})
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await JobLeaseService.release(db, lease, retry_after_seconds=0)
            await db.execute(
                text("UPDATE hf_creation_job SET lease_until=clock_timestamp()-interval '1 second' WHERE job_id=:id"),
                {'id': identity},
            )
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await JobLeaseService.renew(db, lease)

    async def test_finished_blocked_and_unscheduled_not_claimed(self):
        await self.seed(idempotency_key='finished', orchestration_state='5')
        await self.seed(idempotency_key='blocked', orchestration_state='6')
        identity = await self.seed(idempotency_key='not-scheduled')
        async with self.sessions() as db:
            await db.execute(
                text('UPDATE hf_creation_job SET next_action_time=NULL WHERE job_id=:id'), {'id': identity}
            )
            await db.commit()
        self.assertEqual(await self.claim('worker'), [])

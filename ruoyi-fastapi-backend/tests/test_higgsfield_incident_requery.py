"""重新查询沿用核查阶段，不能创建新的提交意图。"""
import os
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from tests import test_higgsfield_incident_archive_action as recovery
from module_higgsfield.entity.vo.incident_action_vo import IncidentAction
from module_higgsfield.service.incident_requery_service import IncidentRequeryService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.dao.price_source_dao import PriceSourceDao


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class IncidentRequeryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = recovery.IncidentArchiveActionTests.asyncSetUp
    cleanup_schema = recovery.IncidentArchiveActionTests.cleanup_schema
    create = recovery.IncidentArchiveActionTests.create
    scope = recovery.IncidentArchiveActionTests.scope
    job = recovery.IncidentArchiveActionTests.job
    call = recovery.IncidentArchiveActionTests.call

    async def requery(self, key=None):
        async with self.sessions() as db:
            return await IncidentRequeryService.requery(db, self.actor, self.job_id,
                IncidentAction(revision='1', action='requery', reason='重新核查保存的响应'), key or str(uuid4()))

    async def test_replay_and_worker_receives_reconciliation_only(self):
        with self.assertRaises(ServiceWarning):
            await self.requery()
        await self.scope('4')
        key = str(uuid4())
        first, replayed = await self.requery(key)
        self.assertFalse(replayed)
        second, replayed = await self.requery(key)
        self.assertTrue(replayed)
        self.assertEqual(first, second)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            leases = await JobLeaseService.claim(db, 'incident-test', kinds=('image',))
        self.assertEqual(len(leases), 1)
        self.assertEqual(leases[0].action, 'reconcile_submission')

    async def test_active_lease_unsupported_stage_and_audit_rollback(self):
        await self.scope('1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET lease_owner='busy',lease_until=clock_timestamp()+interval '1 minute'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.requery()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET lease_owner=NULL,lease_until=NULL,orchestration_state='0'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.requery()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='3'"))
            await db.commit()
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计失败'))):
            with self.assertRaises(RuntimeError):
                await self.requery()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)

    async def test_video_requires_existing_task_and_claims_poll(self):
        await self.scope('1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET kind='video',orchestration_state='4',upstream_state='2',upstream_task_id=NULL"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.requery()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET upstream_task_id='existing-task'"))
            await db.commit()
        await self.requery()
        async with self.sessions() as db:
            leases = await JobLeaseService.claim(db, 'incident-video', kinds=('video',))
            self.assertEqual(leases[0].action, 'poll')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)

    async def test_unknown_video_schedules_evidence_recovery_without_new_call(self):
        await self.scope('1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET kind='video',upstream_task_id=NULL"))
            await db.commit()
        key = str(uuid4())
        first, replayed = await self.requery(key)
        self.assertFalse(replayed)
        second, replayed = await self.requery(key)
        self.assertTrue(replayed)
        self.assertEqual(first, second)
        async with self.sessions() as db:
            leases = await JobLeaseService.claim(db, 'incident-video-recovery', kinds=('video',))
            self.assertEqual(leases[0].action, 'reconcile_submission')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

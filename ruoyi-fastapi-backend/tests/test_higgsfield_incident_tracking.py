"""关闭追踪保留上游与费用未知事实，并让任务退出自动领取。"""
import os
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from tests import test_higgsfield_incident_archive_action as recovery
from module_higgsfield.entity.vo.incident_action_vo import IncidentAction
from module_higgsfield.service.incident_tracking_service import IncidentTrackingService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.dao.price_source_dao import PriceSourceDao


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class IncidentTrackingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = recovery.IncidentArchiveActionTests.asyncSetUp
    cleanup_schema = recovery.IncidentArchiveActionTests.cleanup_schema
    create = recovery.IncidentArchiveActionTests.create
    scope = recovery.IncidentArchiveActionTests.scope
    job = recovery.IncidentArchiveActionTests.job
    call = recovery.IncidentArchiveActionTests.call

    async def close(self, key=None):
        async with self.sessions() as db:
            return await IncidentTrackingService.close(db, self.actor, self.job_id,
                IncidentAction(revision='1', action='close_tracking', reason='人工接管核实', evidenceRef='ticket:123'), key or str(uuid4()))

    async def test_close_stops_claim_without_rewriting_facts_and_rechecks_replay(self):
        with self.assertRaises(ServiceWarning):
            await self.close()
        await self.scope('4')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET upstream_state='6',billing_state='3',next_action_time=clock_timestamp()"))
            await db.commit()
        key = str(uuid4())
        first, replayed = await self.close(key)
        self.assertFalse(replayed)
        second, replayed = await self.close(key)
        self.assertTrue(replayed)
        self.assertEqual(first, second)
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT orchestration_state,upstream_state,billing_state,next_action_time,finished_time FROM hf_creation_job'))).one()
            self.assertEqual(tuple(row), ('6', '6', '3', None, None))
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
            self.assertEqual(await JobLeaseService.claim(db, 'closed-tracking-test'), [])
            await db.execute(text("DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms='operations:recover')"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.close(key)

    async def test_active_lease_and_audit_failure_do_not_close(self):
        await self.scope('1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET lease_owner='busy',lease_until=clock_timestamp()+interval '1 minute'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.close()
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_creation_job SET lease_owner=NULL,lease_until=NULL'))
            await db.commit()
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计故障'))):
            with self.assertRaises(RuntimeError):
                await self.close()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)


class TrackingInputTests(unittest.TestCase):
    def test_evidence_required(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            IncidentAction(revision='1', action='close_tracking', reason='关闭')

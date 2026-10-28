"""明确拒绝证据只能核实同一提交，不覆盖历史或重新消费。"""
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from tests import test_higgsfield_incident_archive_action as recovery
from module_higgsfield.entity.vo.incident_action_vo import IncidentAction
from module_higgsfield.service.incident_rejection_service import IncidentRejectionService
from module_higgsfield.service.incident_read_service import IncidentReadService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class IncidentRejectionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = recovery.IncidentArchiveActionTests.cleanup_schema
    create = recovery.IncidentArchiveActionTests.create
    scope = recovery.IncidentArchiveActionTests.scope
    job = recovery.IncidentArchiveActionTests.job
    call = recovery.IncidentArchiveActionTests.call

    async def asyncSetUp(self):
        await recovery.IncidentArchiveActionTests.asyncSetUp(self)
        await self.scope('4')
        async with self.sessions() as db:
            # 本测试构造从未返回输出的未知提交。
            await db.execute(text('DELETE FROM hf_generated_output'))
            await db.execute(text("UPDATE hf_provider_call SET operation='image',state='3',started_time=clock_timestamp(),finished_time=clock_timestamp() WHERE call_id=:id"), {'id': self.call_id})
            evidence = self.call(job_id=self.job_id, operation='video_poll', state='2',
                acceptance='not_applicable', http_status=200, request_metadata={'submissionCallId': str(self.call_id)},
                response_metadata={'acceptance': 'rejected', 'transport': 'response', 'httpStatus': 200})
            from datetime import datetime, UTC
            evidence.started_time = evidence.finished_time = datetime.now(UTC)
            db.add(evidence)
            await db.flush()
            self.evidence_id = evidence.call_id
            await db.commit()

    async def confirm(self, reference=None, key=None):
        async with self.sessions() as db:
            return await IncidentRejectionService.confirm(db, self.actor, self.job_id,
                IncidentAction(revision='1', action='confirm_not_accepted', reason='核对明确拒绝响应',
                               evidenceRef=reference or f'provider-call:{self.evidence_id}'), key or str(uuid4()))

    async def test_confirm_replay_preserves_original_call_and_billing(self):
        async with self.sessions() as db:
            detail = await IncidentReadService.detail(db, self.actor, self.job_id)
            self.assertIn('confirm_not_accepted', detail['allowedActions'])
            self.assertIn(f'provider-call:{self.evidence_id}', detail['evidenceRefs'])
        key = str(uuid4())
        first, replayed = await self.confirm(key=key)
        self.assertFalse(replayed)
        again, replayed = await self.confirm(key=key)
        self.assertTrue(replayed)
        self.assertEqual(first, again)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT orchestration_state,upstream_state,billing_state FROM hf_creation_job'))).one(), ('5','4','0'))
            self.assertEqual(await db.scalar(text('SELECT acceptance FROM hf_provider_call WHERE call_id=:id'), {'id': self.call_id}), 'unknown')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 3)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

    async def test_arbitrary_reference_wrong_account_and_output_conflict_rejected(self):
        with self.assertRaises(ServiceWarning):
            await self.confirm('ticket:123')
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_provider_call SET account_id=99 WHERE call_id=:id'), {'id': self.evidence_id})
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.confirm()
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_provider_call SET account_id=1 WHERE call_id=:id'), {'id': self.evidence_id})
            await db.execute(text("INSERT INTO hf_generated_output(job_id,ordinal,kind,archive_state,create_time,update_time) VALUES (:id,0,'image','3',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"), {'id': self.job_id})
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.confirm()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)

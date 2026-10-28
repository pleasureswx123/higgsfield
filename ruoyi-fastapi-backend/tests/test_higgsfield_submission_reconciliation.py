"""核查证据绑定及原始调用历史保留；不请求真实供应商。"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.submission_reconciliation_service import SubmissionReconciliationService
from tests import test_higgsfield_provider_call_recovery as recovery


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = recovery.CallRecoveryTests.cleanup_schema
    migrate = recovery.CallRecoveryTests.migrate
    job = recovery.CallRecoveryTests.job
    expire = recovery.CallRecoveryTests.expire

    async def asyncSetUp(self) -> None:
        await recovery.CallRecoveryTests.asyncSetUp(self)
        await self.expire()
        async with self.sessions() as db:
            self.lease = (await JobLeaseService.claim(db, 'reconcile'))[0]

    async def evidence(self, *, accepted: bool = True, account: int | None = None) -> int:
        async with self.sessions() as db:
            original = await ProviderCallDao.locked(db, self.call_id)
            now = await db.scalar(text('SELECT clock_timestamp()'))
            facts = {'acceptance': 'accepted' if accepted else 'unknown', 'transport': 'response', 'httpStatus': 200}
            if accepted:
                facts['upstreamTaskId'] = 'verified-task'
            row = await ProviderCallDao.add(
                db,
                {
                    'job_id': original.job_id,
                    'account_id': account or original.account_id,
                    'credential_version_id': original.credential_version_id,
                    'operation': 'video_poll',
                    'request_hash': 'b' * 64,
                    'request_metadata': {
                        'submissionCallId': str(self.call_id),
                        'fencingToken': str(self.lease.fencing_token),
                    },
                    'state': '2',
                    'acceptance': 'not_applicable',
                    'http_status': 200,
                    'response_metadata': facts,
                    'started_time': now,
                    'finished_time': now,
                    'create_time': now,
                    'update_time': now,
                    'create_by': 'test',
                    'update_by': 'test',
                },
            )
            identity = row.call_id
            await db.commit()
            return identity

    async def test_confirmed_fact_preserves_original_unknown_and_budget(self) -> None:
        identity = await self.evidence()
        async with self.sessions() as db:
            await SubmissionReconciliationService.record(db, self.lease, self.call_id, identity)
            row = (
                await db.execute(text('SELECT orchestration_state,upstream_task_id,billing_state FROM hf_creation_job'))
            ).one()
            self.assertEqual(tuple(row), ('4', 'verified-task', '0'))
            self.assertEqual(
                await db.scalar(text('SELECT state FROM hf_provider_call WHERE call_id=:id'), {'id': self.call_id}), '3'
            )
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_wrong_account_and_event_failure_do_not_confirm(self) -> None:
        wrong = await self.evidence(account=999999)
        good = await self.evidence()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await SubmissionReconciliationService.record(db, self.lease, self.call_id, wrong)
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件失败'))),
                self.assertRaises(RuntimeError),
            ):
                await SubmissionReconciliationService.record(db, self.lease, self.call_id, good)
            self.assertIsNone(await db.scalar(text('SELECT upstream_task_id FROM hf_creation_job')))
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')

    async def test_inconclusive_query_defers_without_new_state_event(self) -> None:
        identity = await self.evidence(accepted=False)
        async with self.sessions() as db:
            await SubmissionReconciliationService.record(db, self.lease, self.call_id, identity)
            row = (
                await db.execute(
                    text('SELECT orchestration_state,upstream_state,lease_owner,event_sequence FROM hf_creation_job')
                )
            ).one()
            self.assertEqual(tuple(row), ('3', '6', None, 4))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

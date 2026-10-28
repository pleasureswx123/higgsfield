"""发送中断恢复同步调用事实，事件失败时保留原发送状态。"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.provider_submission_result_service import ProviderSubmissionResultService
from tests import test_higgsfield_provider_submission_result as submission


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CallRecoveryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = submission.SubmissionResultTests.cleanup_schema
    migrate = submission.SubmissionResultTests.migrate
    job = submission.SubmissionResultTests.job
    asyncSetUp = submission.SubmissionResultTests.asyncSetUp

    async def expire(self) -> None:
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET lease_until=clock_timestamp()-interval '1 second', "
                    "next_action_time=clock_timestamp()-interval '1 second'"
                )
            )
            await db.commit()

    async def test_recovery_preserves_evidence_budget_and_blocks_old_response(self) -> None:
        await self.expire()
        async with self.sessions() as db:
            lease = (await JobLeaseService.claim(db, 'recovery'))[0]
            self.assertEqual(lease.action, 'reconcile_submission')
            row = (
                await db.execute(
                    text(
                        'SELECT state,acceptance,http_status,response_id,response_metadata,request_hash '
                        'FROM hf_provider_call'
                    )
                )
            ).one()
            self.assertEqual(tuple(row[:4]), ('3', 'unknown', None, None))
            self.assertEqual(row[4], {'recoveryReason': 'submission_lease_lost'})
            self.assertEqual(row[5], 'a' * 64)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            with self.assertRaises(ServiceWarning):
                await ProviderSubmissionResultService.record(
                    db,
                    self.lease,
                    self.call_id,
                    ProviderSubmissionResult(
                        acceptance='accepted', transport='response', httpStatus=200, upstreamTaskId='late'
                    ),
                )
            await JobLeaseService.release(db, lease, retry_after_seconds=0)
            await JobLeaseService.claim(db, 'next-recovery')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            self.assertEqual(await db.scalar(text('SELECT event_sequence FROM hf_creation_job')), 4)

    async def test_event_failure_rolls_back_call_and_job(self) -> None:
        await self.expire()
        async with self.sessions() as db:
            with (
                patch.object(JobLeaseDao, 'recovery_event', AsyncMock(side_effect=RuntimeError('恢复事件失败'))),
                self.assertRaises(RuntimeError),
            ):
                await JobLeaseService.claim(db, 'recovery')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            self.assertEqual(
                await db.scalar(text('SELECT fencing_token FROM hf_creation_job')), self.lease.fencing_token
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 3)

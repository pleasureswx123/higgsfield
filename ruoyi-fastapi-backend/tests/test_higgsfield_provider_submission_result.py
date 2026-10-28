"""异步响应事实、未知状态、原租约绑定和事件回滚验证。"""

import os
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.provider_submission_result_service import ProviderSubmissionResultService
from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
from tests import test_higgsfield_provider_submit_intent as intent


class SubmissionResultInputTests(unittest.TestCase):
    def test_transport_uncertainty_and_safe_metadata(self) -> None:
        for value in (
            {'acceptance': 'accepted', 'transport': 'timeout'},
            {'acceptance': 'rejected', 'transport': 'network_error'},
            {'acceptance': 'accepted', 'transport': 'response', 'httpStatus': 500, 'upstreamTaskId': 'id'},
            {'acceptance': 'unknown', 'transport': 'response', 'httpStatus': 200, 'responseId': 'https://secret/url'},
            {'acceptance': 'unknown', 'transport': 'timeout', 'rawResponse': 'secret'},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ProviderSubmissionResult(**value)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class SubmissionResultTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = intent.SubmitIntentTests.cleanup_schema
    migrate = intent.SubmitIntentTests.migrate
    job = intent.SubmitIntentTests.job

    async def asyncSetUp(self) -> None:
        await intent.SubmitIntentTests.asyncSetUp(self)
        async with self.sessions() as db:
            self.lease, self.call_id = await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)

    async def test_accepted_and_duplicate_response_rejected(self) -> None:
        async with self.sessions() as db:
            result = ProviderSubmissionResult(
                acceptance='accepted',
                transport='response',
                httpStatus=200,
                upstreamTaskId='task-1',
                responseId='response-1',
            )
            await ProviderSubmissionResultService.record(db, self.lease, self.call_id, result)
            with self.assertRaises(ServiceWarning):
                await ProviderSubmissionResultService.record(db, self.lease, self.call_id, result)
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_task_id,upstream_response_id,billing_state FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(tuple(row), ('4', 'task-1', 'response-1', '0'))
            self.assertEqual(await db.scalar(text('SELECT acceptance FROM hf_provider_call')), 'accepted')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_explicit_rejection_finishes_execution_without_assuming_free(self) -> None:
        async with self.sessions() as db:
            result = ProviderSubmissionResult(
                acceptance='rejected', transport='response', httpStatus=400, businessCode='invalid_request'
            )
            await ProviderSubmissionResultService.record(db, self.lease, self.call_id, result)
            row = (
                await db.execute(
                    text('SELECT orchestration_state,upstream_state,billing_state,lease_owner FROM hf_creation_job')
                )
            ).one()
            self.assertEqual(tuple(row), ('5', '4', '0', None))
            self.assertEqual(await db.scalar(text('SELECT acceptance FROM hf_provider_call')), 'rejected')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_event_failure_rollback_then_timeout_retains_budget(self) -> None:
        async with self.sessions() as db:
            result = ProviderSubmissionResult(acceptance='unknown', transport='timeout')
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))),
                self.assertRaises(RuntimeError),
            ):
                await ProviderSubmissionResultService.record(db, self.lease, self.call_id, result)
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            await db.rollback()
            await ProviderSubmissionResultService.record(db, self.lease, self.call_id, result)
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '3')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

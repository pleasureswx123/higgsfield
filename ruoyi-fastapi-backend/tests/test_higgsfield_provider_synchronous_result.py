"""同步输出原子完成与失败回滚，不将临时地址写入调用事实。"""

import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSynchronousResult
from module_higgsfield.service.provider_synchronous_result_service import ProviderSynchronousResultService
from tests import test_higgsfield_provider_submission_result as submission
from tests.test_higgsfield_output_discovery import crypto


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class SynchronousResultTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = submission.SubmissionResultTests.cleanup_schema
    migrate = submission.SubmissionResultTests.migrate
    job = submission.SubmissionResultTests.job

    async def asyncSetUp(self) -> None:
        await submission.SubmissionResultTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'sync_outputs', submission.intent.pipeline.MIGRATIONS / '20261027_33_generated_outputs.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.result = ProviderSynchronousResult(
            httpStatus=200,
            responseId='response-sync',
            outputs=[{'ordinal': 0, 'kind': 'image', 'sourceUrl': 'https://example.com/image?key=secret'}],
        )

    async def test_complete_and_old_lease_rejected(self) -> None:
        async with self.sessions() as db:
            db.autoflush = False
            await ProviderSynchronousResultService.record(db, self.lease, self.call_id, self.result, crypto=crypto())
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_state,upstream_response_id,upstream_task_id,billing_state '
                        'FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(tuple(row), ('5', '3', 'response-sync', None, '0'))
            call = (await db.execute(text('SELECT state,acceptance,response_metadata FROM hf_provider_call'))).one()
            self.assertEqual(call[:2], ('2', 'accepted'))
            self.assertEqual(call[2], {'mode': 'synchronous', 'outputCount': 1})
            output = (
                await db.execute(text('SELECT source_url_ciphertext,archive_state FROM hf_generated_output'))
            ).one()
            self.assertNotIn(b'secret', output[0])
            self.assertEqual(output[1], '0')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            with self.assertRaises(ServiceWarning):
                await ProviderSynchronousResultService.record(
                    db, self.lease, self.call_id, self.result, crypto=crypto()
                )

    async def test_event_failure_and_wrong_kind_preserve_sending(self) -> None:
        async with self.sessions() as db:
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))),
                self.assertRaises(RuntimeError),
            ):
                await ProviderSynchronousResultService.record(
                    db, self.lease, self.call_id, self.result, crypto=crypto()
                )
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 0)
            await db.rollback()
            invalid = ProviderSynchronousResult(
                httpStatus=200, outputs=[{'ordinal': 0, 'kind': 'text', 'text': '错误类型'}]
            )
            with self.assertRaises(ServiceWarning):
                await ProviderSynchronousResultService.record(db, self.lease, self.call_id, invalid, crypto=crypto())
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')

"""用量追加与原始调用绑定，重复证据不产生新修订，失败可随外层事务回滚。"""

import importlib.util
import os
import unittest

from sqlalchemy import text

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService
from module_higgsfield.service.usage_record_service import UsageRecordService
from tests import test_higgsfield_provider_submission_result as submission


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class UsageRecordTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = submission.SubmissionResultTests.cleanup_schema
    migrate = submission.SubmissionResultTests.migrate
    job = submission.SubmissionResultTests.job

    async def asyncSetUp(self):
        await submission.SubmissionResultTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'usage_append', submission.intent.pipeline.MIGRATIONS / '20261027_38_usage_records.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_repeated_evidence_and_revisions_do_not_sum(self):
        fact = UsageNormalizationService.image({'input_tokens': 10, 'output_tokens': 20})
        async with self.sessions() as db:
            job, now = await JobLeaseService.guard(db, self.lease)
            call = await ProviderCallDao.locked(db, self.call_id)
            call.state, call.acceptance, call.finished_time = '2', 'accepted', now
            first, added = await UsageRecordService.append(db, job, call, fact, now=now, worker='test')
            self.assertTrue(added)
            again, added = await UsageRecordService.append(db, job, call, fact, now=now, worker='test')
            self.assertFalse(added)
            self.assertEqual(first.usage_id, again.usage_id)
            corrected = UsageNormalizationService.image({'input_tokens': 10, 'output_tokens': 15})
            second, added = await UsageRecordService.append(db, job, call, corrected, now=now, worker='test')
            self.assertTrue(added)
            self.assertEqual((second.revision_no, second.output_tokens), (2, 15))
            self.assertEqual(first.output_tokens, 20)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 2)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')
            await db.commit()

    async def test_outer_rollback_removes_subject_and_usage(self):
        async with self.sessions() as db:
            job, now = await JobLeaseService.guard(db, self.lease)
            call = await ProviderCallDao.locked(db, self.call_id)
            call.state, call.acceptance, call.finished_time = '2', 'accepted', now
            await UsageRecordService.append(
                db, job, call, UsageNormalizationService.image(None), now=now, worker='test'
            )
            await db.rollback()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 0)
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')

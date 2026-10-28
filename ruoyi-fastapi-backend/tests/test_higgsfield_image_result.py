"""图片同步结果原子登记、部分归档和请求级用量证据。"""

import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.entity.vo.image_provider_fact_vo import ImageProviderFact, ProviderImage
from module_higgsfield.service.image_result_service import ImageResultService
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService
from tests import test_higgsfield_provider_synchronous_result as synchronous


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ImageResultTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = synchronous.SynchronousResultTests.cleanup_schema
    migrate = synchronous.SynchronousResultTests.migrate
    job = synchronous.SynchronousResultTests.job

    async def asyncSetUp(self):
        await synchronous.SynchronousResultTests.asyncSetUp(self)
        async with self.sessions() as db:
            exists = await db.scalar(text("SELECT to_regclass('hf_stored_file')"))
        if not exists:
            spec = importlib.util.spec_from_file_location(
                'image_files', synchronous.submission.intent.pipeline.MIGRATIONS / '20261027_06_assets.py'
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location(
            'image_usage', synchronous.submission.intent.pipeline.MIGRATIONS / '20261027_38_usage_records.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.fact = ImageProviderFact(
            response_id='image-result',
            images=[ProviderImage(ordinal=0, data=b'private')],
            usage={'input_tokens': '12', 'output_tokens': '34'},
            usage_fact=UsageNormalizationService.image({'input_tokens': 12, 'output_tokens': 34}),
            rejected_ordinals=[1],
        )
        self.files = {
            0: dict(
                storage_key='media/' + 'd' * 32,
                sha256='e' * 64,
                byte_size=100,
                mime_type='image/png',
                width=16,
                height=16,
            )
        }

    async def test_partial_archive_preserves_ordinals_and_usage_once(self):
        async with self.sessions() as db:
            await ImageResultService.record(db, self.lease, self.call_id, self.fact, self.files)
            rows = (
                await db.execute(text('SELECT ordinal,archive_state,file_id FROM hf_generated_output ORDER BY ordinal'))
            ).all()
            self.assertEqual([(row[0], row[1]) for row in rows], [(0, '2'), (1, '3')])
            self.assertIsNotNone(rows[0][2])
            self.assertIsNone(rows[1][2])
            metadata = await db.scalar(text('SELECT response_metadata FROM hf_provider_call'))
            self.assertEqual(metadata['usage'], {'input_tokens': '12', 'output_tokens': '34'})
            self.assertEqual(metadata['unarchivedOrdinals'], [1])
            self.assertNotIn('private', str(metadata))
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            self.assertEqual(await GeneratedOutputDao.archive_candidates(db, await JobLeaseDao.now(db), 10), [])

    async def test_event_error_rolls_back_files_outputs_and_call(self):
        async with self.sessions() as db:
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件失败'))),
                self.assertRaises(RuntimeError),
            ):
                await ImageResultService.record(db, self.lease, self.call_id, self.fact, self.files)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 0)
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')

"""管理测试按成本中心登记消费对象，未知和实际用量不可混淆。"""
import os
import unittest
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from tests import test_higgsfield_credential_test_executor as executors
from tests import test_higgsfield_credential_image_probe as probes


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestUsageTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = executors.CredentialTestExecutorTests.asyncSetUp
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def test_actual_usage_appends_without_replacing_unknown_or_duplicating_subject(self):
        self.executor.procurement_currency = 'USD'
        self.response = probes.CredentialImageProbeTests().response(usage={'input_tokens': 11, 'output_tokens': 23})
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        self.assertTrue(await self.executor.execute(identity))
        self.assertFalse(await self.executor.execute(identity))
        async with self.sessions() as db:
            subject = (await db.execute(text('SELECT * FROM hf_billing_subject'))).mappings().one()
            self.assertEqual(subject['subject_kind'], 'test')
            self.assertEqual(subject['cost_center_id'], 1)
            self.assertIsNone(subject['job_id'])
            rows = (await db.execute(text('SELECT * FROM hf_usage_record ORDER BY revision_no'))).mappings().all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['completeness'], 'unknown')
            self.assertIsNone(rows[0]['input_tokens'])
            self.assertIsNone(rows[0]['output_tokens'])
            self.assertEqual(rows[1]['completeness'], 'available')
            self.assertEqual((rows[1]['input_tokens'], rows[1]['output_tokens']), (11, 23))
            self.assertEqual(rows[1]['subject_id'], subject['subject_id'])
            self.assertEqual(rows[1]['call_id'], subject['origin_call_id'])
            self.assertIsNone(rows[1]['image_count'])
            metadata = await db.scalar(text('SELECT request_metadata FROM hf_provider_call'))
            self.assertEqual(metadata['procurementPricing'], {'state': 'unpriced',
                'reason': 'MODEL_VARIANT_UNAVAILABLE', 'currency': 'USD'})

    async def test_subject_registration_failure_prevents_sending_and_rolls_back(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        with patch('module_higgsfield.service.credential_test_intent_service.CredentialTestUsageService.append',
                   new=AsyncMock(side_effect=RuntimeError('模拟用量登记失败'))):
            with self.assertRaises(RuntimeError):
                await self.executor.execute(int(receipt['data']['id']))
        self.assertEqual(self.calls, 0)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 0)
            self.assertIsNone(await db.scalar(text('SELECT provider_call_id FROM hf_credential_test')))

"""进程中断后按证据恢复，不把超时当作可重新发送的理由。"""
import asyncio
import os
import unittest
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from tests import test_higgsfield_credential_test_executor as executors
from module_higgsfield.service.credential_test_recovery_service import CredentialTestRecoveryService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestRecoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = executors.CredentialTestExecutorTests.asyncSetUp
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def age(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_call SET started_time=clock_timestamp()-interval '120 seconds'"))
            await db.commit()

    async def test_recent_intent_waits_then_unknown_without_resend(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        self.cancel = True
        with self.assertRaises(asyncio.CancelledError):
            await self.executor.execute(identity)
        recovery = CredentialTestRecoveryService(self.executor, stale_after_seconds=60)
        self.assertFalse(await recovery.recover(identity))
        await self.age()
        self.assertTrue(await recovery.recover(identity))
        self.assertFalse(await recovery.recover(identity))
        self.assertFalse(await self.executor.execute(identity))
        self.assertEqual(self.calls, 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '3')
            self.assertEqual((await db.scalar(text('SELECT result FROM hf_credential_test')))['issue'], 'EXECUTION_INTERRUPTED')

    async def test_registered_response_recovers_after_completion_crash(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        with patch('module_higgsfield.service.credential_test_executor_service.CredentialTestCompletionService.finish',
                   new=AsyncMock(side_effect=RuntimeError('模拟完成事务之前中断'))):
            with self.assertRaises(RuntimeError):
                await self.executor.execute(identity)
        await self.age()
        recovery = CredentialTestRecoveryService(self.executor, stale_after_seconds=60)
        # 文件暂不可用不能覆盖原有证据或错误宣称通过，恢复文件服务后可重试读取。
        with patch.object(self.evidence, 'load', new=AsyncMock(side_effect=ValueError('模拟证据校验失败'))):
            with self.assertRaises(ValueError):
                await recovery.recover(identity)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_test')), '0')
        self.assertTrue(await recovery.recover(identity))
        self.assertFalse(await recovery.recover(identity))
        self.assertFalse(await self.executor.execute(identity))
        self.assertEqual(self.calls, 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_test')), '1')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_test_response')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 1)

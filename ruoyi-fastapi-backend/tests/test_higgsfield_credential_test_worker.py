"""队列读取隔离数据库，失败任务不会阻塞后续受理项。"""
import os
import unittest
from unittest.mock import patch, AsyncMock
from tests import test_higgsfield_credential_test_executor as executors
from module_higgsfield.service.credential_test_worker_service import CredentialTestWorker


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestWorkerTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = executors.CredentialTestExecutorTests.asyncSetUp
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def test_run_once_handles_queue_without_resending(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        worker = CredentialTestWorker(self.executor)
        self.assertEqual(await worker.run_once(), [{'testId': receipt['data']['id'], 'status': 'handled'}])
        self.assertEqual(await worker.run_once(), [])
        self.assertEqual(self.calls, 1)

    async def test_failed_oldest_moves_behind_other_pending_tests(self):
        first, _ = await self.request()
        second, _ = await self.request()
        worker = CredentialTestWorker(self.executor, concurrency=1)
        with patch.object(self.executor, 'execute', new=AsyncMock(side_effect=ValueError('不应输出的秘密'))):
            result = await worker.run_once()
        self.assertEqual(result, [{'testId': first['data']['id'], 'status': 'failed'}])
        self.assertEqual(await worker.run_once(), [{'testId': second['data']['id'], 'status': 'handled'}])
        self.assertEqual(self.calls, 0)


class CredentialWorkerConfigurationTests(unittest.TestCase):
    def test_recovery_window_exceeds_processing_deadline(self):
        for values in ({'concurrency': 0}, {'handler_timeout': 0}, {'handler_timeout': 600},
                       {'stale_after_seconds': 360}):
            with self.assertRaises(ValueError):
                CredentialTestWorker(None, **values)

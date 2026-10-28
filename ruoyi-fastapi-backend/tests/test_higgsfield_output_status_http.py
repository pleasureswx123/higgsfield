"""作品工作状态入口复用登录链、字符串修订与幂等信封。"""
import unittest
from unittest.mock import AsyncMock, patch
from exceptions.exception import AuthException
from module_higgsfield.service.output_status_service import OutputStatusService
from tests import test_higgsfield_output_asset_http as setup


class OutputStatusHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = setup.OutputAssetHttpTests.asyncSetUp
    authenticate = setup.OutputAssetHttpTests.authenticate

    async def test_authentication_and_input_boundaries(self):
        with patch.object(OutputStatusService, 'update', AsyncMock()) as update:
            with self.assertRaises(AuthException):
                await self.client.post('/api/v1/outputs/1/work-status')
            self.authenticate()
            for body, headers in (
                ({'revision': '1', 'workStatus': 'review'}, {}),
                ({'revision': '1', 'workStatus': 'archived'}, {'Idempotency-Key': 'output-status-test-001'}),
                ({'revision': '1', 'workStatus': 'approved', 'archiveState': 'archived'}, {'Idempotency-Key': 'output-status-test-001'}),
            ):
                response = await self.client.post('/api/v1/outputs/1/work-status', json=body, headers=headers)
                self.assertEqual(response.status_code, 422)
            update.assert_not_awaited()

    async def test_replay_preserves_bigint_revision_and_identity(self):
        self.authenticate()
        body = {'code': 200, 'data': {'id': '9007199254740993', 'workStatus': 'review'}}
        with patch.object(OutputStatusService, 'update', AsyncMock(return_value=(body, True))) as update:
            response = await self.client.post('/api/v1/outputs/9007199254740993/work-status',
                json={'revision': '9007199254740994', 'workStatus': 'review', 'reason': '待检查'},
                headers={'Idempotency-Key': 'output-status-test-001'})
            self.assertEqual(response.json(), body)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            self.assertEqual(update.await_args.args[2], 9007199254740993)
            self.assertEqual(update.await_args.args[3].revision, '9007199254740994')

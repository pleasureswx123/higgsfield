"""凭据测试与启用的真实ASGI路由契约；认证和业务服务使用替身。"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.annotation.log_annotation import Log
from common.context import RequestContext
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_admin.service.log_service import LogQueueService
from module_higgsfield.controller.credential_controller import credential_controller
from module_higgsfield.controller.credential_test_controller import credential_test_controller
from module_higgsfield.controller.cost_center_controller import cost_center_controller
from module_higgsfield.service.credential_test_service import CredentialTestService
from module_higgsfield.service.credential_test_model_service import CredentialTestModelService
from module_higgsfield.service.credential_activation_service import CredentialActivationService
from module_higgsfield.service.cost_center_service import CostCenterService


class CredentialWorkflowHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.routers = (credential_controller, credential_test_controller, cost_center_controller)
        for router in self.routers:
            self.app.include_router(router)
        self.user = SimpleNamespace(permissions=['*:*:*'], user=SimpleNamespace(user_id=1, user_name='接口测试', dept=None))
        self.db = object()
        async def database():
            yield self.db
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticate(self):
        async def actor():
            return self.user
        for router in self.routers:
            for dependency in router.dependencies:
                self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_read_routes_require_authentication_and_preserve_pagination(self):
        routes = (
            ('/api/admin/v1/credential-versions/9007199254740993/tests', CredentialTestService, 'listing'),
            ('/api/admin/v1/credential-versions/9007199254740993/test-models', CredentialTestModelService, 'listing'),
            ('/api/admin/v1/cost-centers', CostCenterService, 'listing'),
        )
        for path, owner, method in routes:
            with patch.object(owner, method, AsyncMock()) as service:
                with self.assertRaises(AuthException):
                    await self.client.get(path)
                service.assert_not_awaited()
        self.authenticate()
        for path, owner, method in routes:
            with patch.object(owner, method, AsyncMock(return_value=PageModel(rows=[], total=0, pageNum=2, pageSize=5, hasNext=False))) as service:
                response = await self.client.get(path, params={'pageNum': 2, 'pageSize': 5})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['rows'], [])
                self.assertEqual(service.await_args.args[-1].page_num, 2)
                self.assertEqual((await self.client.get(path, params={'pageSize': 101})).status_code, 422)
                self.assertEqual(service.await_count, 1)

    async def test_mutation_dispatch_idempotency_and_redacted_validation(self):
        self.authenticate()
        operations = (
            ('tests', CredentialTestService, 'create', {'costCenterId': '7', 'modelVersionId': '8', 'acknowledgePotentialCharge': True}),
            ('activate', CredentialActivationService, 'activate', {'revision': '2', 'testId': '9', 'expectedConfigHash': 'a'*64, 'reason': ' 审阅成功测试 '}),
        )
        key = 'credential-http-idempotency-001'
        response_body = {'code': 200, 'data': {'id': '9'}}
        with ExitStack() as stack:
            stack.enter_context(patch.object(RequestContext, 'get_current_user', return_value=self.user))
            stack.enter_context(patch.object(Log, '_get_oper_location', AsyncMock(return_value='测试')))
            logs = stack.enter_context(patch.object(LogQueueService, 'enqueue_operation_log', AsyncMock()))
            for action, owner, method, payload in operations:
                with patch.object(owner, method, AsyncMock(return_value=(response_body, True))) as service:
                    path = f'/api/admin/v1/credential-versions/9007199254740993/{action}'
                    response = await self.client.post(path, json=payload, headers={'Idempotency-Key': key})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), response_body)
                    self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
                    self.assertEqual(service.await_args.args[2], 9007199254740993)
                    self.assertEqual(service.await_args.args[-1], key)
                    self.assertEqual((await self.client.post(path, json=payload)).status_code, 422)
                    invalid = await self.client.post(path, json=payload | {'apiKey': 'must-not-echo-secret'}, headers={'Idempotency-Key': key})
                    self.assertEqual(invalid.status_code, 422)
                    self.assertNotIn('must-not-echo-secret', invalid.text)
                    self.assertEqual(service.await_count, 1)
            self.assertEqual(logs.await_count, 2)
        with patch.object(CredentialTestService, 'create', AsyncMock()) as service:
            for acknowledgement in (False, 1, 'true'):
                response = await self.client.post('/api/admin/v1/credential-versions/1/tests',
                    json={'costCenterId': '7', 'acknowledgePotentialCharge': acknowledgement}, headers={'Idempotency-Key': key})
                self.assertEqual(response.status_code, 422)
            service.assert_not_awaited()

    async def test_detail_forwards_only_service_cost_projection(self):
        self.authenticate()
        result = {'id': '9', 'state': 'passed', 'costVisibility': 'hidden'}
        with patch.object(CredentialTestService, 'get', AsyncMock(return_value=result)) as service:
            response = await self.client.get('/api/admin/v1/credential-tests/9')
            self.assertEqual(response.json()['data'], result)
            self.assertNotIn('cost', response.json()['data'])
            self.assertEqual(service.await_args.args[-1], 9)

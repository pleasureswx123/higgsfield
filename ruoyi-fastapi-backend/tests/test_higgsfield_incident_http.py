"""异常治理 ASGI 契约验证；依赖替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.incident_read_controller import incident_read_controller
from module_higgsfield.service.incident_read_service import IncidentReadService
from contextlib import ExitStack
from common.annotation.log_annotation import Log
from common.context import RequestContext
from module_admin.service.log_service import LogQueueService
from module_higgsfield.service.generation_archive_retry_service import GenerationArchiveRetryService
from module_higgsfield.service.incident_requery_service import IncidentRequeryService
from module_higgsfield.service.incident_tracking_service import IncidentTrackingService
from module_higgsfield.service.incident_rejection_service import IncidentRejectionService


class IncidentHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(incident_read_controller)
        self.user = SimpleNamespace(permissions=['operations:read'], user=SimpleNamespace(user_id=1))
        self.db = object()

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticate(self):
        async def actor():
            return self.user

        for dependency in incident_read_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_missing_authentication_and_list_contract(self):
        path = '/api/admin/v1/generation-incidents'
        with patch.object(IncidentReadService, 'listing', AsyncMock()) as listing:
            with self.assertRaises(AuthException):
                await self.client.get(path)
            listing.assert_not_awaited()
        self.authenticate()
        page = PageModel(rows=[], total=0, pageNum=2, pageSize=5, hasNext=False)
        with patch.object(IncidentReadService, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get(path, params={'projectId': '9007199254740993', 'state': 'source_expired', 'pageNum': 2, 'pageSize': 5})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['rows'], [])
            query = listing.await_args.args[2]
            self.assertEqual((query.project_id, query.state, query.page_num), ('9007199254740993', 'source_expired', 2))
            for params in ({'state': 'invalid'}, {'projectId': '0'}, {'pageSize': 101}):
                self.assertEqual((await self.client.get(path, params=params)).status_code, 422)
            self.assertEqual(listing.await_count, 1)

    async def test_mutation_validation_and_dispatch_preserves_idempotency(self):
        self.authenticate()
        services = {
            'retry_archive': (GenerationArchiveRetryService, 'retry_managed'),
            'requery': (IncidentRequeryService, 'requery'),
            'close_tracking': (IncidentTrackingService, 'close'),
            'confirm_not_accepted': (IncidentRejectionService, 'confirm'),
        }
        response_body = {'code': 200, 'data': {'jobId': '9007199254740993', 'accepted': True}}
        path = '/api/admin/v1/generation-incidents/9007199254740993/actions'
        key = 'incident-http-idempotency-001'
        with ExitStack() as stack:
            # 测试替身提供认证上下文和日志队列；保留真实路由、校验及日志装饰器。
            self.user.user.user_name = '接口测试'
            self.user.user.dept = None
            stack.enter_context(patch.object(RequestContext, 'get_current_user', return_value=self.user))
            logs = stack.enter_context(patch.object(LogQueueService, 'enqueue_operation_log', AsyncMock()))
            stack.enter_context(patch.object(Log, '_get_oper_location', AsyncMock(return_value='测试')))
            mocks = {action: stack.enter_context(patch.object(owner, method, AsyncMock(return_value=(response_body, True)))) for action, (owner, method) in services.items()}
            for action in services:
                payload = {'revision': '7', 'action': action, 'reason': ' 核对证据 ', 'evidenceRef': 'provider-call:9'}
                response = await self.client.post(path, json=payload, headers={'Idempotency-Key': key})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), response_body)
                self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
                args = mocks[action].await_args.args
                self.assertEqual(args[2], 9007199254740993)
                self.assertEqual(args[3].reason, '核对证据')
                self.assertEqual(args[3].action, action)
                self.assertEqual(args[4], key)
            for mock in mocks.values():
                self.assertEqual(mock.await_count, 1)
            self.assertEqual(logs.await_count, 4)
            for payload in (
                {'revision': '7', 'action': 'close_tracking', 'reason': '关闭'},
                {'revision': '7', 'action': 'confirm_not_accepted', 'reason': '确认'},
                {'revision': '7', 'action': 'restart', 'reason': '重启'},
                {'revision': '0', 'action': 'requery', 'reason': '查询'},
                {'revision': '7', 'action': 'retry_archive', 'reason': ' '},
            ):
                self.assertEqual((await self.client.post(path, json=payload, headers={'Idempotency-Key': key})).status_code, 422)
            payload = {'revision': '7', 'action': 'requery', 'reason': '查询'}
            self.assertEqual((await self.client.post(path, json=payload)).status_code, 422)
            for mock in mocks.values():
                self.assertEqual(mock.await_count, 1)


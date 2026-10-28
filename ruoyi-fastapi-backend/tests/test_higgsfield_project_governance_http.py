"""项目治理 ASGI 契约校验；认证替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.project_governance_controller import project_governance_controller
from module_higgsfield.service.project_governance_service import ProjectGovernanceService


class ProjectGovernanceHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(project_governance_controller)
        self.user = SimpleNamespace(permissions=['project:govern'], user=SimpleNamespace(user_id=1))
        self.db = object()

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticate(self):
        async def actor():
            return self.user

        for dependency in project_governance_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_missing_authentication_does_not_reach_service(self):
        with patch.object(ProjectGovernanceService, 'listing', AsyncMock()) as listing:
            with self.assertRaises(AuthException):
                await self.client.get('/api/admin/v1/projects')
            listing.assert_not_awaited()

    async def test_list_query_and_framework_pagination(self):
        self.authenticate()
        row = {'id': '9007199254740993', 'name': '测试项目', 'revision': '2', 'status': 'paused'}
        page = PageModel(rows=[row], total=4, pageNum=2, pageSize=1, hasNext=True)
        with patch.object(ProjectGovernanceService, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get('/api/admin/v1/projects', params={
                'q': '测试%', 'status': 'paused', 'pageNum': 2, 'pageSize': 1,
            })
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['code'], 200)
            self.assertEqual(body['rows'], [row])
            self.assertEqual(body['total'], 4)
            query = listing.await_args.args[2]
            self.assertEqual((query.q, query.status, query.page_num, query.page_size), ('测试%', 'paused', 2, 1))
            for params in ({'status': 'deleted'}, {'pageNum': 0}, {'pageSize': 101}, {'q': 'x' * 201}):
                self.assertEqual((await self.client.get('/api/admin/v1/projects', params=params)).status_code, 422)
            self.assertEqual(listing.await_count, 1)

    async def test_invalid_mutation_never_reaches_service(self):
        self.authenticate()
        payload = {'revision': '1', 'action': 'pause', 'reason': '维护'}
        headers = {'Idempotency-Key': 'governance-http-test-001'}
        path = '/api/admin/v1/projects/1/governance'
        with patch.object(ProjectGovernanceService, 'change', AsyncMock()) as change:
            self.assertEqual((await self.client.post(path, json=payload)).status_code, 422)
            for changes in ({'action': 'delete'}, {'reason': ' '}, {'revision': '0'}, {'unexpected': True}):
                response = await self.client.post(path, json=payload | changes, headers=headers)
                self.assertEqual(response.status_code, 422, changes)
            for identity in ('0', '-1', '9223372036854775808', 'abc'):
                response = await self.client.post(f'/api/admin/v1/projects/{identity}/governance', json=payload, headers=headers)
                self.assertEqual(response.status_code, 422)
            change.assert_not_awaited()

    async def test_openapi_requires_idempotency_and_body(self):
        paths = self.app.openapi()['paths']
        self.assertIn('get', paths['/api/admin/v1/projects'])
        operation = paths['/api/admin/v1/projects/{project_id}/governance']['post']
        header = next(value for value in operation['parameters'] if value['name'] == 'Idempotency-Key')
        self.assertTrue(header['required'])
        self.assertTrue(operation['requestBody']['required'])

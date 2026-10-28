"""归档恢复 HTTP 输入与权限门槛；认证替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.context import RequestContext
from exceptions.exception import AuthException, PermissionException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.project_controller import project_controller
from module_higgsfield.service.project_lifecycle_service import ProjectLifecycleService


class LifecycleHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(project_controller)
        self.user = SimpleNamespace(permissions=['project:archive'], user=SimpleNamespace(user_id=1))
        async def database():
            yield object()
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticate(self):
        async def actor():
            token = RequestContext.set_current_user(self.user)
            try:
                yield self.user
            finally:
                RequestContext.reset_current_user(token)
        for dependency in project_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_authentication_and_function_permission(self):
        with patch.object(ProjectLifecycleService, 'change', AsyncMock()) as change:
            with self.assertRaises(AuthException):
                await self.client.post('/api/v1/projects/1/archive', json={'revision': '1', 'reason': '完结'})
            self.authenticate()
            self.user.permissions = ['project:read']
            with self.assertRaises(PermissionException):
                await self.client.post('/api/v1/projects/1/restore', json={'revision': '2'},
                    headers={'Idempotency-Key': 'project-lifecycle-http'})
            change.assert_not_awaited()

    async def test_input_contract_and_openapi(self):
        self.authenticate()
        with patch.object(ProjectLifecycleService, 'change', AsyncMock()) as change:
            for action in ('archive', 'restore'):
                path = f'/api/v1/projects/1/{action}'
                payload = {'revision': '1', 'reason': '完结'}
                self.assertEqual((await self.client.post(path, json=payload)).status_code, 422)
                for invalid in ({'revision': '0'}, {'unexpected': True}):
                    self.assertEqual((await self.client.post(path, json=payload | invalid,
                        headers={'Idempotency-Key': 'project-lifecycle-http'})).status_code, 422)
            self.assertEqual((await self.client.post('/api/v1/projects/1/archive',
                json={'revision': '1', 'reason': '  '},
                headers={'Idempotency-Key': 'project-lifecycle-http'})).status_code, 422)
            change.assert_not_awaited()
        paths = self.app.openapi()['paths']
        for action in ('archive', 'restore'):
            operation = paths[f'/api/v1/projects/{{project_id}}/{action}']['post']
            self.assertTrue(operation['requestBody']['required'])
            self.assertTrue(next(p for p in operation['parameters'] if p['name'] == 'Idempotency-Key')['required'])

    async def test_rename_patch_permission_and_validation(self):
        self.authenticate()
        path = '/api/v1/projects/1'
        headers = {'Idempotency-Key': 'project-rename-http'}
        with patch.object(ProjectLifecycleService, 'change', AsyncMock()) as change:
            with self.assertRaises(PermissionException):
                await self.client.patch(path, json={'revision': '1', 'name': '名称'}, headers=headers)
            self.user.permissions = ['project:manage']
            for payload in ({'revision': '1'}, {'revision': '1', 'name': ' '},
                            {'revision': '0', 'name': '名称'}, {'revision': '1', 'name': '名称', 'reason': '多余'}):
                self.assertEqual((await self.client.patch(path, json=payload, headers=headers)).status_code, 422)
            change.assert_not_awaited()
        operation = self.app.openapi()['paths']['/api/v1/projects/{project_id}']['patch']
        self.assertTrue(operation['requestBody']['required'])

    async def test_pause_resume_http_contract(self):
        self.authenticate()
        headers = {'Idempotency-Key': 'project-pause-http'}
        with patch.object(ProjectLifecycleService, 'change', AsyncMock()) as change:
            with self.assertRaises(PermissionException):
                await self.client.post('/api/v1/projects/1/pause', json={'revision': '1', 'reason': '维护'}, headers=headers)
            self.user.permissions = ['project:manage']
            for action, body in (('pause', {'revision': '1'}), ('pause', {'revision': '1', 'reason': ' '}), ('resume', {'revision': '0'})):
                self.assertEqual((await self.client.post(f'/api/v1/projects/1/{action}', json=body, headers=headers)).status_code, 422)
            change.assert_not_awaited()
        for action in ('pause', 'resume'):
            operation = self.app.openapi()['paths'][f'/api/v1/projects/{{project_id}}/{action}']['post']
            self.assertTrue(next(p for p in operation['parameters'] if p['name'] == 'Idempotency-Key')['required'])

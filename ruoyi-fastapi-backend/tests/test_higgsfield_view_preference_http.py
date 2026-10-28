"""视图偏好 HTTP 范围和输入边界，不替代真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.view_preference_controller import view_preference_controller as router
from module_higgsfield.service.view_preference_service import ViewPreferenceService as Service


class ViewPreferenceHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI(); self.app.include_router(router)
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield object()
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Idempotency-Key': 'view-preference-http-test'}

    def authenticate(self):
        async def actor():
            return self.user
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_login_scope_and_replay(self):
        with self.assertRaises(AuthException):
            await self.client.get('/api/v1/view-preferences/projects')
        self.authenticate()
        with patch.object(Service, 'get', AsyncMock(return_value={'revision': '0'})) as read:
            response = await self.client.get('/api/v1/view-preferences/library', params={'projectId': '9007199254740993'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(read.await_args.args[3], 9007199254740993)
        result = {'code': 200, 'data': {'revision': '1'}}
        with patch.object(Service, 'put', AsyncMock(return_value=(result, True))) as write:
            response = await self.client.put('/api/v1/view-preferences/elements', headers=self.headers,
                json={'revision': '0', 'settings': {'layout': 'board'}, 'projectId': '9007199254740993'})
            self.assertEqual(response.json(), result)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            self.assertEqual(write.await_args.args[3].project_id, '9007199254740993')

    async def test_unknown_views_and_invalid_identifiers_do_not_reach_service(self):
        self.authenticate()
        with patch.object(Service, 'put', AsyncMock()) as write:
            for view, body in [('unknown', {'revision': '0', 'settings': {}}),
                               ('projects', {'revision': 0, 'settings': {}}),
                               ('library', {'revision': '0', 'settings': {}, 'projectId': '9223372036854775808'}),
                               ('projects', {'revision': '0', 'settings': {}, 'userId': '2'})]:
                response = await self.client.put('/api/v1/view-preferences/' + view, headers=self.headers, json=body)
                self.assertEqual(response.status_code, 422)
            response = await self.client.put('/api/v1/view-preferences/projects', json={'revision': '0', 'settings': {}})
            self.assertEqual(response.status_code, 422); write.assert_not_awaited()

"""个人导航接口契约，依赖替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.project_preference_controller import project_preference_controller as router
from module_higgsfield.service.project_preference_service import PreferenceService as Service


class PreferenceHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI(); self.app.include_router(router)
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield object()
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Idempotency-Key': 'personal-navigation-http-test'}

    def authenticate(self):
        async def actor():
            return self.user
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_login_and_patch_presence(self):
        with self.assertRaises(AuthException):
            await self.client.get('/api/v1/project-collections')
        self.authenticate()
        result = {'code': 200, 'data': {'revision': '2'}}
        with patch.object(Service, 'put_preference', AsyncMock(return_value=(result, True))) as put:
            response = await self.client.put('/api/v1/projects/9007199254740993/preferences',
                json={'revision': '1', 'collectionId': None}, headers=self.headers)
            self.assertEqual(response.json(), result)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            self.assertEqual(put.await_args.args[2], 9007199254740993)
            self.assertEqual(put.await_args.args[3], {'revision': '1', 'collectionId': None})
        with patch.object(Service, 'mutate_collection', AsyncMock(return_value=(result, False))) as mutate:
            response = await self.client.patch('/api/v1/project-collections/3',
                json={'revision': '1', 'color': None}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mutate.await_args.args[3], {'revision': '1', 'color': None})

    async def test_invalid_body_and_delete_revision(self):
        self.authenticate()
        with patch.object(Service, 'put_preference', AsyncMock()) as put:
            for payload in ({'revision': '0'}, {'revision': 0, 'isPinned': True},
                            {'revision': '0', 'isPinned': 'true'}, {'revision': '0', 'userId': '2'}):
                response = await self.client.put('/api/v1/projects/1/preferences', json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 422)
            response = await self.client.put('/api/v1/projects/1/preferences', json={'revision': '0', 'isPinned': True})
            self.assertEqual(response.status_code, 422); put.assert_not_awaited()
        with patch.object(Service, 'mutate_collection', AsyncMock()) as mutate:
            for revision in ('0', '9223372036854775808'):
                response = await self.client.delete('/api/v1/project-collections/1', params={'revision': revision}, headers=self.headers)
                self.assertEqual(response.status_code, 422)
            mutate.assert_not_awaited()

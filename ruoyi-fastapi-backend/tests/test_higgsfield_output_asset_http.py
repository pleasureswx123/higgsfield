"""作品转素材路由的登录、输入和幂等参数边界。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.output_controller import output_controller as router
from module_higgsfield.service.output_asset_service import OutputAssetService as Service


class OutputAssetHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.db = object()
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield self.db
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticate(self):
        async def actor():
            return self.user
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_login_required(self):
        with patch.object(Service, 'create', AsyncMock()) as create:
            with self.assertRaises(AuthException):
                await self.client.post('/api/v1/outputs/1/to-asset')
            create.assert_not_awaited()

    async def test_request_and_replay_preserve_identity(self):
        self.authenticate()
        body = {'code': 200, 'data': {'id': '9007199254740995'}}
        with patch.object(Service, 'create', AsyncMock(return_value=(body, True))) as create:
            response = await self.client.post('/api/v1/outputs/9007199254740993/to-asset',
                json={'projectId': '9007199254740994', 'name': '参考素材'},
                headers={'Idempotency-Key': 'output-to-asset-http-001'})
            self.assertEqual(response.json(), body)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            args = create.await_args.args
            self.assertEqual(args[:3], (self.db, self.user, 9007199254740993))
            self.assertEqual(args[3].project_id, '9007199254740994')
            self.assertEqual(args[4], 'output-to-asset-http-001')

    async def test_missing_key_or_invalid_destination_rejected(self):
        self.authenticate()
        payload = {'projectId': '1', 'name': '素材'}
        with patch.object(Service, 'create', AsyncMock()) as create:
            response = await self.client.post('/api/v1/outputs/1/to-asset', json=payload)
            self.assertEqual(response.status_code, 422)
            for fields in ({'projectId': 1}, {'name': ' '}, {'folderId': '-1'}, {'fileId': '9'}):
                response = await self.client.post('/api/v1/outputs/1/to-asset', json=payload | fields,
                    headers={'Idempotency-Key': 'output-to-asset-http-001'})
                self.assertEqual(response.status_code, 422)
            create.assert_not_awaited()

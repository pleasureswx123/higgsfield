"""收藏ASGI契约测试，身份注入不代表真实JWT端到端验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.favorite_controller import favorite_controller as router
from module_higgsfield.service.favorite_service import FavoriteService as Service


class FavoriteHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.db = object()
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1), permissions=['*:*:*'])
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

    async def test_all_routes_require_login(self):
        with patch.object(Service, 'create', AsyncMock()) as create, patch.object(Service, 'listing', AsyncMock()) as listing, patch.object(Service, 'cancel', AsyncMock()) as cancel:
            for method, path in [('POST', ''), ('GET', ''), ('DELETE', '/1')]:
                with self.assertRaises(AuthException):
                    await self.client.request(method, '/api/v1/favorites' + path)
            for call in (create, listing, cancel):
                call.assert_not_awaited()

    async def test_create_preserves_bigint_and_optional_key_and_replay(self):
        self.authenticate()
        body = {'code': 200, 'data': {'id': '9007199254740995', 'target': {'assetId': '9007199254740993'}}}
        with patch.object(Service, 'create', AsyncMock(return_value=(body, True))) as create:
            response = await self.client.post('/api/v1/favorites', json={'target': {'assetId': '9007199254740993'}})
            self.assertEqual(response.json(), body)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            args = create.await_args.args
            self.assertEqual(args[:2], (self.db, self.user))
            self.assertEqual(args[2].target.asset_id, '9007199254740993')
            self.assertIsNone(args[3])

    async def test_invalid_targets_and_identity_cannot_reach_service(self):
        self.authenticate()
        with patch.object(Service, 'create', AsyncMock()) as create, patch.object(Service, 'cancel', AsyncMock()) as cancel:
            for payload in ({'target': {}}, {'target': {'assetId': 1}}, {'target': {'assetId': '0'}},
                            {'target': {'assetId': '1', 'outputId': '2'}}, {'target': {'assetId': '1'}, 'userId': '2'}):
                response = await self.client.post('/api/v1/favorites', json=payload)
                self.assertEqual(response.status_code, 422, payload)
            for identity in ('0', '-1', 'abc'):
                self.assertEqual((await self.client.delete('/api/v1/favorites/' + identity)).status_code, 422)
            create.assert_not_awaited()
            cancel.assert_not_awaited()

    async def test_pagination_aliases_and_unavailable_rows_remain_top_level(self):
        self.authenticate()
        page = PageModel(rows=[{'id': '9', 'kind': 'output', 'target': {'outputId': '7'}, 'available': False}], total=1, pageNum=1, pageSize=30, hasNext=False)
        with patch.object(Service, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get('/api/v1/favorites', params={'kind': 'output', 'pageNum': 1, 'pageSize': 30})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('data', response.json())
            self.assertFalse(response.json()['rows'][0]['available'])
            self.assertNotIn('source', response.json()['rows'][0])
            self.assertEqual(listing.await_args.args[2].page_size, 30)
            for query in ({'kind': 'other'}, {'pageSize': 101}, {'pageNum': 0}):
                self.assertEqual((await self.client.get('/api/v1/favorites', params=query)).status_code, 422)

    async def test_cancel_forwards_identity_and_key(self):
        self.authenticate()
        body = {'code': 200, 'data': {'id': '9007199254740993', 'cancelled': True}}
        with patch.object(Service, 'cancel', AsyncMock(return_value=(body, False))) as cancel:
            response = await self.client.delete('/api/v1/favorites/9007199254740993', headers={'Idempotency-Key': 'favorite-cancel-http-001'})
            self.assertEqual(response.json(), body)
            self.assertEqual(cancel.await_args.args, (self.db, self.user, 9007199254740993, 'favorite-cancel-http-001'))

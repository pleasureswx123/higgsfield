"""调用记录 ASGI 契约验证；依赖替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.provider_call_read_controller import provider_call_read_controller
from module_higgsfield.service.provider_call_read_service import ProviderCallReadService


class ProviderCallHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(provider_call_read_controller)
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

        for dependency in provider_call_read_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_missing_authentication_and_read_only_routes(self):
        with patch.object(ProviderCallReadService, 'listing', AsyncMock()) as listing, patch.object(ProviderCallReadService, 'detail', AsyncMock()) as detail:
            for path in ('/api/admin/v1/provider-calls', '/api/admin/v1/provider-calls/1'):
                with self.assertRaises(AuthException):
                    await self.client.get(path)
            listing.assert_not_awaited()
            detail.assert_not_awaited()
        for path in self.app.openapi()['paths'].values():
            self.assertEqual(set(path), {'get'})

    async def test_list_filters_and_framework_page(self):
        self.authenticate()
        page = PageModel(rows=[], total=0, pageNum=2, pageSize=5, hasNext=False)
        with patch.object(ProviderCallReadService, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get('/api/admin/v1/provider-calls', params={
                'jobId': '9007199254740993', 'accountId': '7', 'state': 'unknown',
                'from': '2026-10-01T08:00:00+08:00', 'pageNum': 2, 'pageSize': 5,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['rows'], [])
            self.assertEqual(response.json()['total'], 0)
            query = listing.await_args.args[2]
            self.assertEqual((query.job_id, query.account_id, query.state), ('9007199254740993', '7', 'unknown'))
            self.assertEqual(query.from_time.isoformat(), '2026-10-01T00:00:00+00:00')
            for params in ({'state': '2'}, {'accountId': '0'}, {'pageSize': 101}, {'from': '2026-10-01T00:00:00'}):
                self.assertEqual((await self.client.get('/api/admin/v1/provider-calls', params=params)).status_code, 422)
            self.assertEqual(listing.await_count, 1)

    async def test_detail_string_identity_and_response_envelope(self):
        self.authenticate()
        result = {'id': '9007199254740993', 'requestMetadata': {'modelVersionId': '7'}, 'responseMetadata': {}}
        with patch.object(ProviderCallReadService, 'detail', AsyncMock(return_value=result)) as detail:
            response = await self.client.get('/api/admin/v1/provider-calls/9007199254740993')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['code'], 200)
            self.assertEqual(response.json()['data'], result)
            detail.assert_awaited_once_with(self.db, self.user, 9007199254740993)
            for identity in ('0', '-1', '9223372036854775808', 'abc'):
                self.assertEqual((await self.client.get(f'/api/admin/v1/provider-calls/{identity}')).status_code, 422)
            self.assertEqual(detail.await_count, 1)

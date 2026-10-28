"""费用路由的ASGI契约验证；依赖替身不代表真实登录业务端到端验收。"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.billing_controller import billing_controller
from module_higgsfield.service.billing_admin_service import BillingAdminService
from common.vo import PageModel


class BillingHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_parses_from_to_and_rejects_ambiguous_time_windows(self):
        self.authenticated_stub()
        path = '/api/admin/v1/billing-events'
        page = PageModel(rows=[], total=0, pageNum=1, pageSize=20, hasNext=False)
        with patch.object(BillingAdminService, 'listing', AsyncMock(return_value=page)) as listing:
            result = await self.client.get(
                path, params={'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00'}
            )
            self.assertEqual(result.status_code, 200)
            query = listing.await_args.args[2]
            self.assertEqual(query.from_time.isoformat(), '2026-10-31T16:00:00+00:00')
            for params in (
                {'from': '2026-11-01T00:00:00'},
                {'from': '2026-11-02T00:00:00Z', 'to': '2026-11-01T00:00:00Z'},
                {'from': '2025-01-01T00:00:00Z', 'to': '2026-11-01T00:00:00Z'},
            ):
                self.assertEqual((await self.client.get(path, params=params)).status_code, 422)
            self.assertEqual(listing.await_count, 1)

    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(billing_controller)
        self.user = SimpleNamespace(permissions=['billing:read'], user=SimpleNamespace(user_id=1))
        self.db = object()

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    def authenticated_stub(self):
        async def actor():
            return self.user

        for dependency in billing_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_missing_authorization_is_rejected_before_detail_service(self):
        with patch.object(BillingAdminService, 'detail', AsyncMock()) as detail:
            with self.assertRaises(AuthException):
                await self.client.get('/api/admin/v1/billing-events/1')
            detail.assert_not_awaited()

    async def test_detail_route_uses_framework_response_and_numeric_path(self):
        self.authenticated_stub()
        result = {'id': '9007199254740993', 'amount': '0.0200000000', 'effectiveAmount': '0.0100000000'}
        with patch.object(BillingAdminService, 'detail', AsyncMock(return_value=result)) as detail:
            response = await self.client.get('/api/admin/v1/billing-events/9007199254740993')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['code'], 200)
            self.assertEqual(response.json()['data'], result)
            detail.assert_awaited_once_with(self.db, self.user, 9007199254740993)
            for identity in ('0', '-1', '9223372036854775808', 'abc'):
                self.assertEqual((await self.client.get(f'/api/admin/v1/billing-events/{identity}')).status_code, 422)
            self.assertEqual(detail.await_count, 1)

    async def test_invalid_adjustment_never_reaches_mutation_service(self):
        self.authenticated_stub()
        path = '/api/admin/v1/billing-events/1/adjustments'
        payload = {'revision': '1', 'deltaAmount': '-0.01', 'reason': '部分退款'}
        with patch.object(BillingAdminService, 'adjust', AsyncMock()) as adjust:
            self.assertEqual((await self.client.post(path, json=payload)).status_code, 422)
            for changes in (
                {'deltaAmount': 0.1},
                {'deltaAmount': '0'},
                {'deltaAmount': '-0.000'},
                {'deltaAmount': '1e2'},
                {'deltaAmount': '0.12345678901'},
                {'reason': ' '},
                {'revision': '0'},
                {'unexpected': 'value'},
            ):
                response = await self.client.post(
                    path, json=payload | changes, headers={'Idempotency-Key': 'test-billing-key-001'}
                )
                self.assertEqual(response.status_code, 422, changes)
            adjust.assert_not_awaited()

    async def test_openapi_registers_both_routes_and_required_idempotency_header(self):
        paths = self.app.openapi()['paths']
        self.assertIn('get', paths['/api/admin/v1/billing-events/{event_id}'])
        operation = paths['/api/admin/v1/billing-events/{event_id}/adjustments']['post']
        header = next(value for value in operation['parameters'] if value['name'] == 'Idempotency-Key')
        self.assertTrue(header['required'])
        self.assertTrue(operation['requestBody']['required'])

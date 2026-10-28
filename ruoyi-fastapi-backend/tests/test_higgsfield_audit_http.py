"""只读审计路由的 ASGI 契约检查，认证替身不代表真实登录。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.audit_read_controller import audit_read_controller
from module_higgsfield.service.audit_read_service import AuditReadService


class AuditHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(audit_read_controller)
        self.user = SimpleNamespace(permissions=['audit:read'], user=SimpleNamespace(user_id=1))
        self.db = object()

        async def database():
            yield self.db

        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_authentication_and_read_only_routes(self):
        with patch.object(AuditReadService, 'listing', AsyncMock()) as listing:
            with self.assertRaises(AuthException):
                await self.client.get('/api/admin/v1/audit-logs')
            listing.assert_not_awaited()
        self.assertEqual(set(self.app.openapi()['paths']['/api/admin/v1/audit-logs']), {'get'})
        self.assertEqual((await self.client.delete('/api/admin/v1/audit-logs')).status_code, 405)

    async def test_query_aliases_and_framework_page(self):
        async def actor():
            return self.user

        for dependency in audit_read_controller.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor
        page = PageModel(rows=[], total=0, pageNum=2, pageSize=5, hasNext=False)
        with patch.object(AuditReadService, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get('/api/admin/v1/audit-logs', params={
                'actorId': '9007199254740993', 'objectType': 'project', 'objectId': 'history-key',
                'from': '2026-10-01T08:00:00+08:00', 'pageNum': 2, 'pageSize': 5,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['rows'], [])
            self.assertEqual(response.json()['total'], 0)
            query = listing.await_args.args[2]
            self.assertEqual(query.actor_id, '9007199254740993')
            self.assertEqual(query.object_id, 'history-key')
            self.assertEqual(query.from_time.isoformat(), '2026-10-01T00:00:00+00:00')
            self.assertEqual((query.page_num, query.page_size), (2, 5))
            self.assertEqual((await self.client.get('/api/admin/v1/audit-logs', params={'actorId': '0'})).status_code, 422)
            self.assertEqual(listing.await_count, 1)

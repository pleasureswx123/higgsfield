"""后台审批HTTP契约；身份和业务Service替身不代表真实登录验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.vo import PageModel
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.project_join_controller import project_join_controller as router
from module_higgsfield.service.project_join_service import ProjectJoinService as Service


class JoinHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI(); self.app.include_router(router)
        self.db, self.user = object(), SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield self.db
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Idempotency-Key': 'join-review-http-contract-001'}

    def authenticate(self):
        async def actor():
            return self.user
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_login_and_no_production_application_route(self):
        for method, path in [('GET', '/projects/1/join-requests'), ('POST', '/join-requests/1/review')]:
            with self.subTest(path=path), self.assertRaises(AuthException):
                await self.client.request(method, '/api/admin/v1' + path)
        paths = self.app.openapi()['paths']
        self.assertEqual(set(paths), {'/api/admin/v1/projects/{project_id}/join-requests', '/api/admin/v1/join-requests/{identity}/review'})

    async def test_page_filters_and_bigint_review_replay(self):
        self.authenticate()
        page = PageModel(rows=[{'id': '9007199254740993'}], total=1, pageNum=2, pageSize=10, hasNext=False)
        with patch.object(Service, 'listing', AsyncMock(return_value=page)) as listing:
            response = await self.client.get('/api/admin/v1/projects/9007199254740993/join-requests', params={'status': 'pending', 'pageNum': 2, 'pageSize': 10})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['rows'][0]['id'], '9007199254740993')
            self.assertEqual(listing.await_args.args[2], 9007199254740993)
            self.assertEqual(listing.await_args.args[3].status, 'pending')
            self.assertEqual(listing.await_args.args[3].page_num, 2)
        result = {'code': 200, 'data': {'id': '9007199254740993', 'status': 'approved'}}
        with patch.object(Service, 'review', AsyncMock(return_value=(result, True))) as review:
            response = await self.client.post('/api/admin/v1/join-requests/9007199254740993/review',
                json={'revision': '3', 'decision': 'approved', 'roleId': '9007199254740994'}, headers=self.headers)
            self.assertEqual(response.json(), result)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            args = review.await_args.args
            self.assertEqual(args[:3], (self.db, self.user, 9007199254740993))
            self.assertEqual(args[3].role_id, '9007199254740994')
            self.assertEqual(args[4], self.headers['Idempotency-Key'])

    async def test_invalid_payload_never_reaches_service(self):
        self.authenticate()
        with patch.object(Service, 'review', AsyncMock()) as review:
            path = '/api/admin/v1/join-requests/1/review'
            for payload in ({'revision': '1', 'decision': 'approved'},
                {'revision': '1', 'decision': 'rejected', 'roleId': '2'},
                {'revision': 1, 'decision': 'rejected'},
                {'revision': '1', 'decision': 'rejected', 'userId': '9'}):
                self.assertEqual((await self.client.post(path, json=payload, headers=self.headers)).status_code, 422)
            self.assertEqual((await self.client.post(path, json={'revision': '1', 'decision': 'rejected'})).status_code, 422)
            review.assert_not_awaited()

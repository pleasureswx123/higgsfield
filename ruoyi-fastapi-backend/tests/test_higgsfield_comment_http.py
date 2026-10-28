"""评论路由认证及修订/标注语义契约；身份和Service使用替身。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.comment_controller import comment_controller as router
from module_higgsfield.service.comment_service import CommentService as Service


class CommentHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.db, self.user = object(), SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield self.db
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.headers = {'Idempotency-Key': 'comment-http-contract-001'}

    def authenticate(self):
        async def actor():
            return self.user
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def test_all_routes_require_login(self):
        for method, path in [('POST', '/comment-threads'), ('GET', '/comment-threads'),
                             ('GET', '/comment-threads/1/comments'), ('POST', '/comment-threads/1/comments'),
                             ('PATCH', '/comments/1'), ('DELETE', '/comments/1')]:
            with self.subTest(method=method, path=path), self.assertRaises(AuthException):
                await self.client.request(method, '/api/v1' + path)

    async def test_patch_preserves_annotation_absence_and_explicit_empty(self):
        self.authenticate()
        body = {'code': 200, 'data': {'id': '9007199254740993', 'revision': '2'}}
        with patch.object(Service, 'mutate', AsyncMock(return_value=(body, True))) as mutate:
            for annotations in ({}, {'annotations': []}):
                response = await self.client.patch('/api/v1/comments/9007199254740993',
                    json={'revision': '1', 'body': '修改'} | annotations, headers=self.headers)
                self.assertEqual(response.json(), body)
                self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
                args = mutate.await_args.args
                self.assertEqual(args[:3], (self.db, self.user, 9007199254740993))
                self.assertEqual('annotations' in args[3].model_fields_set, 'annotations' in annotations)
                self.assertEqual(args[4], self.headers['Idempotency-Key'])

    async def test_delete_uses_query_revision_and_invalid_patch_cannot_write(self):
        self.authenticate()
        with patch.object(Service, 'mutate', AsyncMock(return_value=({'code': 200, 'data': {'deleted': True}}, False))) as mutate:
            response = await self.client.delete('/api/v1/comments/9', params={'revision': '3'}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mutate.await_args.args[3].revision, '3')
            self.assertTrue(mutate.await_args.kwargs['delete'])
            mutate.reset_mock()
            for payload in ({'revision': 1, 'body': '正文'}, {'revision': '1', 'body': ' '},
                            {'revision': '1', 'body': '正文', 'annotations': None},
                            {'revision': '1', 'body': '正文', 'parentId': '8'}):
                response = await self.client.patch('/api/v1/comments/9', json=payload, headers=self.headers)
                self.assertEqual(response.status_code, 422)
            self.assertEqual((await self.client.delete('/api/v1/comments/9', headers=self.headers)).status_code, 422)
            mutate.assert_not_awaited()

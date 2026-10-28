"""真实ASGI路由契约；登录和服务替身不代表认证业务端到端验收。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from common.aspect.db_session import get_db_session_provider
from common.vo import PageModel
from exceptions.exception import AuthException
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.element_import_controller import element_import_controller as router
from module_higgsfield.service.element_import_service import ElementImportService as Imports
from module_higgsfield.service.element_import_edit_service import ElementImportEditService as Edits
from module_higgsfield.service.element_import_confirm_service import ElementImportConfirmService as Confirms


class ElementImportHttpTests(unittest.IsolatedAsyncioTestCase):
    path = '/api/v1/imports/elements'
    headers = {'Idempotency-Key': 'element-import-http-key-001'}

    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.db = object()
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1), permissions=['element:import'])

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

    async def test_all_routes_require_login_before_service(self):
        with (patch.object(Imports, 'create', AsyncMock()) as create, patch.object(Imports, 'get', AsyncMock()) as get,
             patch.object(Imports, 'rows', AsyncMock()) as rows, patch.object(Edits, 'edit', AsyncMock()) as edit,
             patch.object(Confirms, 'confirm', AsyncMock()) as confirm):
            for method, suffix in [('POST', ''), ('GET', '/1'), ('GET', '/1/rows'), ('PATCH', '/1/rows/1'), ('POST', '/1/confirm')]:
                with self.subTest(method=method, suffix=suffix), self.assertRaises(AuthException):
                    await self.client.request(method, self.path + suffix)
            for call in (create, get, rows, edit, confirm):
                call.assert_not_awaited()

    async def test_create_preserves_string_ids_and_replay_header(self):
        self.authenticate()
        payload = {'projectId': '9007199254740993', 'uploadId': '9007199254740994', 'schemaVersion': 1, 'includeProjectName': False}
        body = {'code': 200, 'data': {'id': '9007199254740995', 'accepted': True, 'state': 'pending'}}
        with patch.object(Imports, 'create', AsyncMock(return_value=(body, True))) as create:
            response = await self.client.post(self.path, json=payload, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), body)
            self.assertEqual(response.headers['Idempotent-Replayed'], 'true')
            args = create.await_args.args
            self.assertEqual(args[:2], (self.db, self.user))
            self.assertEqual(args[2].model_dump(by_alias=True), payload)
            self.assertEqual(args[3], self.headers['Idempotency-Key'])

    async def test_invalid_create_and_confirm_do_not_reach_write_service(self):
        self.authenticate()
        payload = {'projectId': '1', 'uploadId': '2', 'schemaVersion': 1}
        with patch.object(Imports, 'create', AsyncMock()) as create, patch.object(Confirms, 'confirm', AsyncMock()) as confirm:
            self.assertEqual((await self.client.post(self.path, json=payload)).status_code, 422)
            for fields in [{'projectId': 1}, {'uploadId': '0'}, {'schemaVersion': True}, {'includeProjectName': 'false'}, {'status': 'finished'}]:
                response = await self.client.post(self.path, json=payload | fields, headers=self.headers)
                self.assertEqual(response.status_code, 422, fields)
            for fields in [{'revision': 2}, {'revision': '0'}, {'revision': '2', 'state': 'finished'}]:
                response = await self.client.post(self.path + '/1/confirm', json=fields, headers=self.headers)
                self.assertEqual(response.status_code, 422, fields)
            self.assertEqual((await self.client.post(self.path + '/1/confirm', json={'revision': '2'})).status_code, 422)
            create.assert_not_awaited()
            confirm.assert_not_awaited()

    async def test_rows_use_top_level_pagination_and_aliases(self):
        self.authenticate()
        page = PageModel(rows=[{'rowNo': 2, 'revision': '9007199254740993', 'issues': []}], total=1, pageNum=1, pageSize=10, hasNext=False)
        with patch.object(Imports, 'rows', AsyncMock(return_value=page)) as rows:
            response = await self.client.get(self.path + '/9007199254740993/rows', params={'pageNum': 1, 'pageSize': 10, 'state': 'failed'})
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertNotIn('data', result)
            self.assertEqual(result['rows'][0]['revision'], '9007199254740993')
            self.assertEqual(result['pageSize'], 10)
            args = rows.await_args.args
            self.assertEqual(args[2], 9007199254740993)
            self.assertEqual(args[3].state, 'failed')
            for params in [{'pageSize': 101}, {'pageNum': 0}, {'state': 'uploaded'}]:
                self.assertEqual((await self.client.get(self.path + '/1/rows', params=params)).status_code, 422)
            self.assertEqual(rows.await_count, 1)

    async def test_edit_optional_key_and_confirm_required_key_dispatch(self):
        self.authenticate()
        payload = {'revision': '1', 'isSelected': False, 'candidate': {'schemaVersion': 1, 'name': '甲', 'alias': '001', 'category': 'character', 'description': '', 'propertyValues': []}}
        body = {'code': 200, 'data': {'revision': '2', 'batchRevision': '3'}}
        with patch.object(Edits, 'edit', AsyncMock(return_value=(body, False))) as edit:
            response = await self.client.patch(self.path + '/11/rows/2', json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Idempotent-Replayed', response.headers)
            self.assertEqual(edit.await_args.args[2:4], (11, 2))
            self.assertIsNone(edit.await_args.args[5])
            self.assertFalse(edit.await_args.args[4].is_selected)
        with patch.object(Confirms, 'confirm', AsyncMock(return_value=({'code': 200, 'data': {'createdCount': 1}}, False))) as confirm:
            response = await self.client.post(self.path + '/11/confirm', json={'revision': '3'}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(confirm.await_args.args[2], 11)
            self.assertEqual(confirm.await_args.args[3].revision, '3')

    async def test_openapi_exposes_expected_routes_and_header_requirements(self):
        paths = self.app.openapi()['paths']
        for suffix, method in [('', 'post'), ('/{identity}', 'get'), ('/{identity}/rows', 'get'), ('/{identity}/rows/{row_no}', 'patch'), ('/{identity}/confirm', 'post')]:
            operation = paths[self.path + suffix][method]
            if method in {'post', 'patch'}:
                header = next(item for item in operation['parameters'] if item['name'] == 'Idempotency-Key')
                self.assertEqual(header['required'], method == 'post')

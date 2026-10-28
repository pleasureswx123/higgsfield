"""缩略图HTTP边界与真实临时文件流；身份/DAO替身不代表真实登录验收。"""
import io
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from PIL import Image
from common.aspect.db_session import get_db_session_provider
from exceptions.handle import handle_exception
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.asset_controller import asset_controller
from module_higgsfield.controller.output_controller import output_controller
from module_higgsfield.dao.media_derivative_dao import MediaDerivativeDao
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from module_higgsfield.service.thumbnail_read_service import ThumbnailReadService


class ThumbnailHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        for router in (asset_controller, output_controller):
            self.app.include_router(router)
        handle_exception(self.app)
        self.db = SimpleNamespace(rollback=AsyncMock())
        self.user = SimpleNamespace(user=SimpleNamespace(user_id=1))
        async def database():
            yield self.db
        self.app.dependency_overrides[get_db_session_provider(None)] = database
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = StorageService(StoragePolicy(self.directory.name, 'local-test', '', 1024 * 1024, 100000))
        buffer = io.BytesIO()
        with Image.new('RGB', (32, 16), 'blue') as picture:
            picture.save(buffer, 'WEBP')
        self.content = buffer.getvalue()
        self.key = 'media/' + 'b' * 32
        with self.storage.open_key(self.key, write=True) as handle:
            handle.write(self.content)
        self.source = SimpleNamespace(file_id=123, state='1', mime_type='image/png')
        self.derived = SimpleNamespace(storage_key=self.key, byte_size=len(self.content), mime_type='image/webp')

    def authenticate(self):
        async def actor():
            return self.user
        for router in (asset_controller, output_controller):
            for dependency in router.dependencies:
                self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor

    async def media(self, db, user, identity, range_header=None, *, head=False, thumbnail=False):
        self.assertIs(db, self.db)
        self.assertIs(user, self.user)
        self.assertEqual(identity, 9007199254740993)
        self.assertTrue(thumbnail)
        return await ThumbnailReadService.stream(db, self.source, range_header, head, self.storage)

    async def test_get_head_and_range_use_authorized_thumbnail_stream(self):
        self.authenticate()
        for prefix, service in (('asset-versions', AssetService), ('outputs', OutputReadService)):
            url = f'/api/v1/{prefix}/9007199254740993/thumbnail'
            with patch.object(service, 'media', side_effect=self.media), patch.object(
                MediaDerivativeDao, 'ready', AsyncMock(return_value=self.derived)
            ):
                response = await self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, self.content)
                self.assertEqual(response.headers['content-type'], 'image/webp')
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
                response = await self.client.get(url, headers={'Range': 'bytes=2-7'})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.content, self.content[2:8])
                self.assertEqual(response.headers['content-range'], f'bytes 2-7/{len(self.content)}')
                response = await self.client.head(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, b'')
                self.assertEqual(int(response.headers['content-length']), len(self.content))
                response = await self.client.get(url, headers={'Range': 'bytes=999999-'})
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response.headers['content-range'], f'bytes */{len(self.content)}')
        self.assertEqual(self.db.rollback.await_count, 6)

    async def test_pending_thumbnail_returns_framework_error_instead_of_image(self):
        self.authenticate()
        for prefix, service in (('asset-versions', AssetService), ('outputs', OutputReadService)):
            with patch.object(service, 'media', side_effect=self.media), patch.object(
                MediaDerivativeDao, 'ready', AsyncMock(return_value=None)
            ):
                response = await self.client.get(f'/api/v1/{prefix}/9007199254740993/thumbnail')
                self.assertIn('application/json', response.headers['content-type'])
                self.assertNotEqual(response.json()['code'], 200)
                self.assertEqual(response.json()['data']['errorCode'], 'THUMBNAIL_NOT_READY')
        self.db.rollback.assert_not_awaited()

    async def test_anonymous_request_cannot_reach_media_service(self):
        for prefix, service in (('asset-versions', AssetService), ('outputs', OutputReadService)):
            with patch.object(service, 'media', AsyncMock()) as media:
                for method in ('GET', 'HEAD'):
                    response = await self.client.request(method, f'/api/v1/{prefix}/1/thumbnail')
                    self.assertNotIn('image/', response.headers.get('content-type', ''))
                    if method == 'GET':
                        self.assertEqual(response.json()['code'], 401)
                media.assert_not_awaited()

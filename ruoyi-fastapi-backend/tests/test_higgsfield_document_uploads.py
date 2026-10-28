"""管理证据真实分片与独立 PostgreSQL schema 验证。"""
import hashlib
import io
import os
import tempfile
import unittest
from uuid import uuid4

from openpyxl import Workbook
from PIL import Image
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.asset_vo import UploadComplete
from module_higgsfield.entity.vo.document_upload_vo import DocumentUploadCreate
from module_higgsfield.service.document_storage_service import DocumentStorageService
from module_higgsfield.service.document_upload_service import DocumentUploadService
from module_higgsfield.service.storage_service import StoragePolicy
from module_higgsfield.service.upload_service import UploadService
from tests import test_higgsfield_assets as assets


class DocumentStorageTests(unittest.TestCase):
    def test_screenshot_content_and_mime(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = DocumentStorageService(StoragePolicy(directory, 'local-test', '', 100000, 1024))
            for format, mime in [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')]:
                buffer = io.BytesIO()
                Image.new('RGB', (16, 16), 'white').save(buffer, format=format)
                data = buffer.getvalue()
                key, digest = storage.put_part(data)
                parts = [{'storage_key': key, 'sha256': digest, 'byte_size': len(data)}]
                result = storage.assemble(parts, len(data), digest, mime)
                self.assertEqual((result['mime_type'], result['width'], result['height']), (mime, 16, 16))
                with self.assertRaises(ServiceWarning):
                    storage.assemble(parts, len(data), digest, 'image/jpeg' if mime != 'image/jpeg' else 'image/png')
            for body in (b'<svg xmlns="http://www.w3.org/2000/svg"/>', b'\x89PNG\r\n\x1a\ninvalid'):
                with self.assertRaises(ServiceWarning):
                    storage.verify_file(io.BytesIO(body), 'image/png')
            storage.policy = StoragePolicy(directory, 'local-test', '', 100000, 100)
            with self.assertRaises(ServiceWarning):
                storage.verify_file(io.BytesIO(assets.png_bytes()), 'image/png')

    def test_content_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = DocumentStorageService(StoragePolicy(directory, 'local-test', '', 100000, 100))
            storage.verify_file(io.BytesIO('名称,价格\n测试,1.25\n'.encode()), 'text/csv')
            for body in (b'a,b\n1\n', b'a,\x00\n', b'\xff\xfe', b''):
                with self.assertRaises(ServiceWarning):
                    storage.verify_file(io.BytesIO(body), 'text/csv')
            with self.assertRaises(ServiceWarning):
                storage.verify_file(io.BytesIO(assets.png_bytes()), 'text/plain')
            book = Workbook()
            book.active.append(['名称', '价格'])
            book.active.append(['测试', 1.25])
            buffer = io.BytesIO()
            book.save(buffer)
            mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            self.assertEqual(storage.verify_file(buffer, mime)['mime_type'], mime)
            with self.assertRaises(ServiceWarning):
                storage.verify_file(io.BytesIO(b'fake workbook'), mime)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class DocumentUploadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        self.owner.user.admin = True
        async with self.engine.begin() as connection:
            await connection.execute(text('ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS dept_id bigint'))
        self.storage = DocumentStorageService(self.storage.policy)

    async def test_roundtrip_replay_and_scope(self):
        data = '名称,金额\n测试,1.23\n'.encode()
        payload = DocumentUploadCreate(purpose='price_source', fileName='价格.csv',
            byteSize=str(len(data)), mimeType='text/csv')
        key = str(uuid4())
        async with self.sessions() as db:
            first, replay = await DocumentUploadService.create(db, self.owner, payload, key, self.storage)
            self.assertFalse(replay)
            upload_id = int(first['data']['id'])
            second, replay = await DocumentUploadService.create(db, self.owner, payload, key, self.storage)
            self.assertTrue(replay)
            self.assertEqual(first, second)
            self.assertIsNone(first['data']['projectId'])
            with self.assertRaises(ServiceWarning):
                await UploadService.get(db, self.owner, upload_id)
            await db.rollback()
            with self.assertRaises(ServiceWarning):
                await DocumentUploadService.get(db, self.other, upload_id)
            await db.rollback()
            async def stream():
                yield data
            digest = hashlib.sha256(data).hexdigest()
            await DocumentUploadService.put_part(db, self.owner, upload_id, 1,
                f'bytes 0-{len(data)-1}/{len(data)}', digest, stream(), self.storage)
            complete_key = str(uuid4())
            complete = UploadComplete(sha256=digest)
            result, _ = await DocumentUploadService.complete(db, self.owner, upload_id, complete, complete_key, self.storage)
            self.assertEqual(result['data']['state'], 'ready')
            repeated, replay = await DocumentUploadService.complete(db, self.owner, upload_id, complete, complete_key, self.storage)
            self.assertTrue(replay)
            self.assertEqual(result, repeated)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            paths = (await db.execute(text('SELECT api_prefix, normalized_path FROM hf_api_idempotency_record WHERE result_type=\'upload\''))).all()
            self.assertTrue(all(prefix == '/api/admin/v1' and path.startswith('/document-uploads') for prefix, path in paths))
            await db.rollback()
            self.owner.permissions = ['billing:reconcile']
            with self.assertRaises(PermissionException):
                await DocumentUploadService.complete(db, self.owner, upload_id, complete, complete_key, self.storage)
            with self.assertRaises(PermissionException):
                await DocumentUploadService.create(db, self.owner, payload, key, self.storage)

"""真实上传、附件唯一绑定及授权下载；不访问供应商或公司 NAS。"""
import asyncio
import hashlib
import io
import os
import tempfile
import unittest
from uuid import uuid4

from sqlalchemy import text
from PIL import Image
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.asset_vo import UploadComplete
from module_higgsfield.entity.vo.document_upload_vo import DocumentUploadCreate
from module_higgsfield.service.document_upload_service import DocumentUploadService
from module_higgsfield.service.document_storage_service import DocumentStorageService
from module_higgsfield.service.storage_service import StoragePolicy
from module_higgsfield.service.price_source_service import PriceSourceService
from tests import test_higgsfield_price_sources as sources


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceAttachmentTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = sources.PriceSourceTests.cleanup_schema
    payload = sources.PriceSourceTests.payload

    async def asyncSetUp(self):
        await sources.PriceSourceTests.asyncSetUp(self)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.storage = DocumentStorageService(StoragePolicy(folder.name, 'local-test', '', 4096, 100))
        self.body = '名称,金额\n测试,1.23\n'.encode()

    async def upload(self, purpose='price_source', complete=True, mime='text/csv', name='报价证据.csv'):
        async with self.sessions() as db:
            receipt, _ = await DocumentUploadService.create(db, self.owner,
                DocumentUploadCreate(purpose=purpose, fileName=name, byteSize=str(len(self.body)),
                    mimeType=mime), str(uuid4()), self.storage)
            identity = int(receipt['data']['id'])
            if complete:
                async def stream():
                    yield self.body
                digest = hashlib.sha256(self.body).hexdigest()
                await DocumentUploadService.put_part(db, self.owner, identity, 1,
                    f'bytes 0-{len(self.body)-1}/{len(self.body)}', digest, stream(), self.storage)
                await DocumentUploadService.complete(db, self.owner, identity, UploadComplete(sha256=digest),
                    str(uuid4()), self.storage)
            return identity

    async def test_official_screenshot_roundtrip(self):
        buffer = io.BytesIO()
        Image.new('RGB', (8, 8), 'white').save(buffer, format='PNG')
        self.body = buffer.getvalue()
        identity = await self.upload(mime='image/png', name='官方报价截图.png')
        async with self.sessions() as db:
            receipt, _ = await PriceSourceService.create(db, self.owner,
                self.payload(sourceType='official_screenshot', sourceUrl=None, uploadId=str(identity)), str(uuid4()))
            self.assertEqual(receipt['data']['attachment']['mimeType'], 'image/png')
            self.assertEqual(await db.scalar(text('SELECT width FROM hf_stored_file')), 8)
            stream, _, mime, _ = await PriceSourceService.download(db, self.owner,
                receipt['data']['id'], storage=self.storage)
            self.assertEqual(mime, 'image/png')
            self.assertEqual(b''.join([chunk async for chunk in stream]), self.body)

    async def test_bind_replay_download_and_retention(self):
        identity = await self.upload()
        payload, key = self.payload(uploadId=str(identity)), str(uuid4())
        async with self.sessions() as db:
            first, _ = await PriceSourceService.create(db, self.owner, payload, key)
            repeated, replay = await PriceSourceService.create(db, self.owner, payload, key)
            self.assertTrue(replay)
            self.assertEqual(first, repeated)
            source_id = first['data']['id']
            self.assertEqual(first['data']['attachment']['fileName'], '报价证据.csv')
            self.assertNotIn('storage_key', str(first))
            with self.assertRaises(ServiceWarning):
                await PriceSourceService.create(db, self.owner, payload, str(uuid4()))
            with self.assertRaises(ServiceWarning):
                await DocumentUploadService.cancel(db, self.owner, identity)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_upload_binding')), 1)
            await db.execute(text("UPDATE hf_upload_session SET expires_time=NOW()-interval '1 hour', create_time=NOW()-interval '2 hours' WHERE upload_id=:id"), {'id': identity})
            await db.commit()
            self.assertEqual((await PriceSourceService.get(db, self.owner, source_id)), first['data'])
            body, headers, mime, status = await PriceSourceService.download(db, self.owner, source_id, storage=self.storage)
            self.assertEqual(b''.join([chunk async for chunk in body]), self.body)
            self.assertEqual(status, 200)
            self.assertEqual(mime, 'text/csv')
            self.assertIn('attachment', headers['Content-Disposition'])
            self.assertEqual(headers['Cache-Control'], 'no-store')
            body, _, _, status = await PriceSourceService.download(db, self.owner, source_id, 'bytes=0-3', storage=self.storage)
            self.assertEqual(status, 206)
            self.assertEqual(b''.join([chunk async for chunk in body]), self.body[:4])
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await PriceSourceService.download(db, self.owner, source_id, storage=self.storage)

    async def test_scope_readiness_and_concurrent_single_binding(self):
        unfinished = await self.upload(complete=False)
        wrong_purpose = await self.upload('reconciliation')
        owned = await self.upload()
        async with self.sessions() as db:
            for identity in (unfinished, wrong_purpose):
                with self.assertRaises(ServiceWarning):
                    await PriceSourceService.create(db, self.owner, self.payload(uploadId=str(identity)), str(uuid4()))
            await db.execute(text('UPDATE hf_upload_session SET owner_id=2 WHERE upload_id=:id'), {'id': owned})
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await PriceSourceService.create(db, self.owner, self.payload(uploadId=str(owned)), str(uuid4()))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_source')), 0)
        target = await self.upload()
        async def bind():
            async with self.sessions() as db:
                return await PriceSourceService.create(db, self.owner, self.payload(uploadId=str(target)), str(uuid4()))
        results = await asyncio.gather(bind(), bind(), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, tuple) for value in results), 1)
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in results), 1)

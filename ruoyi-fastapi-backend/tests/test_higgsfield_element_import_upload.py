"""实际模板字节经分片上传、完整校验后绑定元素导入。"""
import hashlib
import io
import os
import unittest
from uuid import uuid4
from openpyxl import Workbook
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.asset_vo import UploadCreate, UploadComplete, AssetCreate
from module_higgsfield.entity.vo.element_import_vo import ElementImportCreate
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.project_upload_storage_service import ProjectUploadStorageService
from module_higgsfield.service.storage_service import StoragePolicy
from module_higgsfield.service.element_import_service import ElementImportService
from tests import test_higgsfield_element_import_service as imports
from tests import test_higgsfield_assets as assets


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportUploadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = imports.ElementImportServiceTests.cleanup_schema
    create = imports.ElementImportServiceTests.create
    migrate = imports.ElementImportServiceTests.migrate
    send_part = assets.AssetDatabaseTests.send_part

    async def asyncSetUp(self):
        await imports.ElementImportServiceTests.asyncSetUp(self)
        self.storage = ProjectUploadStorageService(StoragePolicy(self.directory.name, 'local-test', '',
                                                  100000, 1024, part_size=1024))

    async def upload(self, body, mime):
        async with self.sessions() as db:
            receipt, _ = await UploadService.create(db, self.owner, UploadCreate(projectId=self.project_id,
                fileName='元素模板', byteSize=str(len(body)), mimeType=mime), str(uuid4()), self.storage)
        identity = int(receipt['data']['id'])
        for offset in range(0, len(body), 1024):
            await self.send_part(identity, body[offset:offset+1024], offset//1024+1, len(body))
        async with self.sessions() as db:
            receipt, _ = await UploadService.complete(db, self.owner, identity,
                UploadComplete(sha256=hashlib.sha256(body).hexdigest()), str(uuid4()), self.storage)
        return identity, receipt

    async def test_csv_and_xlsx_real_bytes_are_bound_without_media_asset(self):
        book = Workbook()
        book.active.append(['名称', '别名', '分类', '描述'])
        book.active.append(['角色', '001', '角色', '说明'])
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        files = [('text/csv', '名称,别名,分类,描述\n角色,001,角色,说明'.encode()),
                 ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', stream.getvalue())]
        for mime, body in files:
            identity, receipt = await self.upload(body, mime)
            self.assertEqual(receipt['data']['state'], 'ready')
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning):
                    await AssetService.bind(db, self.owner, AssetCreate(projectId=self.project_id,
                        uploadId=str(identity), name='不可绑定的模板'), str(uuid4()))
            async with self.sessions() as db:
                result, _ = await ElementImportService.create(db, self.owner,
                    ElementImportCreate(projectId=self.project_id, uploadId=str(identity), schemaVersion=1), str(uuid4()))
                key = await db.scalar(text('SELECT f.storage_key FROM hf_import_job j JOIN hf_stored_file f '
                    'ON f.file_id=j.source_file_id WHERE j.import_id=:id'), {'id': int(result['data']['id'])})
            with self.storage.open_key(key) as handle:
                self.assertEqual(handle.read(), body)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_job')), 2)

    async def test_invalid_workbook_never_becomes_ready(self):
        with self.assertRaises(ServiceWarning):
            await self.upload(b'not-a-workbook', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_job')), 0)

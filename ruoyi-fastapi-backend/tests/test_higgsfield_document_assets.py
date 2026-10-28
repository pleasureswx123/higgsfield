"""真实分片、内容校验、文档绑定及受限原件预览。"""
import hashlib
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.asset_vo import UploadCreate, UploadComplete, AssetCreate, LibraryQuery
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.project_upload_storage_service import ProjectUploadStorageService
from module_higgsfield.service.storage_service import StoragePolicy
from tests import test_higgsfield_assets as assets
from tests.test_higgsfield_pptx_content import document
from module_higgsfield.service.pptx_content_service import PptxContentService
from module_higgsfield.service.docx_content_service import DocxContentService
from tests.test_higgsfield_element_docx_parser import docx


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class DocumentAssetTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        self.storage = ProjectUploadStorageService(StoragePolicy(self.directory.name, 'local-test', '', 100000, 1024, part_size=100000))

    async def upload_bind(self, body, mime, name):
        digest = hashlib.sha256(body).hexdigest()
        async with self.sessions() as db:
            result, _ = await UploadService.create(db, self.owner, UploadCreate(projectId=self.project_id,
                fileName=name, byteSize=str(len(body)), mimeType=mime, sha256=digest), str(uuid4()), self.storage)
            identity = int(result['data']['id'])
        async def content():
            yield body
        async with self.sessions() as db:
            await UploadService.put_part(db, self.owner, identity, 1, f'bytes 0-{len(body)-1}/{len(body)}', digest, content(), self.storage)
        async with self.sessions() as db:
            await UploadService.complete(db, self.owner, identity, UploadComplete(sha256=digest), str(uuid4()), self.storage)
        async with self.sessions() as db:
            return await AssetService.bind(db, self.owner, AssetCreate(projectId=self.project_id, uploadId=str(identity), name=name), str(uuid4()))

    async def test_document_bind_filter_and_safe_raw_preview(self):
        for kind, mime, body in [('txt', 'text/plain', '纯文本'.encode()), ('md', 'text/markdown', b'# heading'),
                                 ('html', 'text/html', b'<html><script>alert(1)</script><p>hello</p></html>'),
                                 ('pptx', PptxContentService.mime, document()),
                                 ('docx', DocxContentService.mime, docx('<w:p><w:r><w:t>正文</w:t></w:r></w:p>'))]:
            with self.subTest(kind=kind):
                result, _ = await self.upload_bind(body, mime, '文档.' + kind)
                asset = result['data']; self.assertEqual(asset['mediaType'], 'document')
                async with self.sessions() as db:
                    page = await AssetService.library(db, self.owner, int(self.project_id), LibraryQuery(fileType=kind))
                    self.assertEqual(page.total, 1); self.assertEqual(page.rows[0]['asset']['id'], asset['id'])
                    stream, headers, output_mime, _ = await AssetService.media(db, self.owner, int(asset['currentVersionId']), storage=self.storage)
                    self.assertIn('sandbox', headers['Content-Security-Policy'])
                    if kind in ('pptx', 'docx'): self.assertEqual(headers['Content-Disposition'], 'attachment')
                    else: self.assertEqual(output_mime, 'text/plain; charset=utf-8')
                    self.assertEqual(b''.join([chunk async for chunk in stream]), body)
                async with self.sessions() as db:
                    preview = await AssetService.document_text(db, self.owner, int(asset['currentVersionId']), self.storage)
                    expected = ['第二页', '第一页'] if kind == 'pptx' else ['正文'] if kind == 'docx' else [body.decode()]
                    self.assertEqual(preview['sections'], expected)
                    self.assertEqual(preview['mimeType'], mime)
                async with self.sessions() as db:
                    with patch.object(self.storage, 'open_key') as opened:
                        with self.assertRaises((PermissionException, ServiceWarning)):
                            await AssetService.document_text(db, self.other, int(asset['currentVersionId']), self.storage)
                        opened.assert_not_called()

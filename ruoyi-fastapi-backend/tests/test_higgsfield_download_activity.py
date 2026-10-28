"""授权下载审计不代表完整传输，使用隔离数据库与本地测试文件。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import PermissionException
from module_higgsfield.entity.vo.asset_vo import AssetCreate, LibraryQuery
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.dao.asset_dao import AssetDao
from tests import test_higgsfield_assets as assets
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class DownloadActivityTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create
    new_upload = assets.AssetDatabaseTests.new_upload
    send_part = assets.AssetDatabaseTests.send_part
    ready_upload = assets.AssetDatabaseTests.ready_upload
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('download_audit', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_16_audit.py')
        self.migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            result, _ = await AssetService.bind(db, self.owner, AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='下载验证'), str(uuid4()))
            self.asset = result['data']
            await db.execute(text("INSERT INTO hf_project_role_permission (role_id,permission_code,data_scope) SELECT role_id,'asset:download','project' FROM hf_project_role WHERE code='owner'"))
            await db.commit()

    async def media(self, download=True, head=False):
        async with self.sessions() as db:
            result = await AssetService.media(db, self.owner, int(self.asset['currentVersionId']), 'bytes=0-7', download=download, head=head, storage=self.storage)
            if result[0] is not None:
                self.assertEqual(b''.join([chunk async for chunk in result[0]]), assets.png_bytes()[:8])
            return result

    async def test_preview_head_and_personal_download_filter(self):
        await self.media(download=False); await self.media(head=True)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)
        await self.media(); await self.media()
        async with self.sessions() as db:
            facts = (await db.execute(text("SELECT before_after FROM hf_audit_log WHERE action='download_authorized'"))).scalars().all()
            self.assertEqual(len(facts), 2); self.assertFalse(facts[0]['authorized']['transferComplete'])
            self.assertEqual(facts[0]['authorized']['byteLength'], '8')
            page = await AssetService.library(db, self.owner, int(self.project_id), LibraryQuery(activity='downloaded'))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['asset']['id'], self.asset['id'])
            _, count = await AssetDao.library(db, int(self.asset['spaceId']), LibraryQuery(activity='downloaded'), 2)
            self.assertEqual(count, 0)
            await db.rollback()

    async def test_audit_failure_and_denial_do_not_record_success(self):
        with patch('module_higgsfield.service.asset_service.AssetDao.add', AsyncMock(side_effect=RuntimeError('审计不可用'))):
            with self.assertRaises(RuntimeError):
                await self.media()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:download'")); await db.commit()
        with self.assertRaises(PermissionException):
            await self.media()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)

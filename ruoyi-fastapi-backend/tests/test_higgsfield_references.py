"""引用候选的权限过滤、精确版本及分页计数验证。"""

import os
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import PermissionException
from module_higgsfield.entity.vo.reference_vo import ReferenceQuery
from module_higgsfield.service.reference_service import ReferenceService
from tests import test_higgsfield_element_copy as copies
from tests import test_higgsfield_document_assets as documents
from module_higgsfield.service.project_upload_storage_service import ProjectUploadStorageService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ReferenceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = copies.ElementCopyTests.cleanup_schema
    create = copies.ElementCopyTests.create
    new_upload = copies.ElementCopyTests.new_upload
    send_part = copies.ElementCopyTests.send_part
    ready_upload = copies.ElementCopyTests.ready_upload

    async def asyncSetUp(self):
        await copies.ElementCopyTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'generation_permission',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_11_generation_permission.py',
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)
            self.assertEqual(
                await conn.scalar(
                    text("SELECT count(*) FROM hf_project_role_permission WHERE permission_code='generation:create'")
                ),
                0,
            )
            await conn.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'generation:create','project' FROM hf_project_role WHERE code='owner'"
                )
            )

    async def search(self, **options):
        async with self.sessions() as db:
            return await ReferenceService.search(db, self.owner, ReferenceQuery(projectId=self.project_id, **options))

    async def test_fixed_revision_and_pagination(self):
        result = await self.search()
        self.assertEqual(result.total, 2)
        element = next(row for row in result.rows if row['kind'] == 'element')
        self.assertEqual(element['elementRevisionId'], self.source['currentRevision']['id'])
        self.assertEqual(element['assetVersionIds'], [self.asset['currentVersionId']])
        self.assertEqual(element['primaryAssetVersionId'], self.asset['currentVersionId'])
        first, second = await self.search(pageSize=1), await self.search(pageSize=1, pageNum=2)
        self.assertEqual(first.total, 2)
        self.assertTrue(first.has_next)
        self.assertNotEqual(first.rows[0]['kind'], second.rows[0]['kind'])
        self.assertEqual((await self.search(q='hero', kind='element')).total, 1)
        async with self.sessions() as db:
            empty = await ReferenceService.search(db, self.owner, ReferenceQuery(projectId=self.target_id))
            self.assertEqual(empty.total, 0)

    async def test_documents_never_become_video_candidates(self):
        self.storage = ProjectUploadStorageService(self.storage.policy)
        result, _ = await documents.DocumentAssetTests.upload_bind(self, b'# document', 'text/markdown', '文档.md')
        document_id = result['data']['id']
        page = await self.search(pageSize=1)
        self.assertEqual(page.total, 2)
        self.assertTrue(page.has_next)
        self.assertNotEqual(page.rows[0]['id'], document_id)
        self.assertEqual((await self.search(kind='asset')).total, 1)
        self.assertEqual((await self.search(q='文档')).total, 0)
        # 异常旧数据中元素指向文档，也不得以图片角色进入候选。
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_element_revision_media SET asset_version_id=:version'),
                             {'version': int(result['data']['currentVersionId'])})
            await db.commit()
        self.assertEqual((await self.search(kind='element')).total, 0)
        # 候选层仅使用已验证文件元数据，视频仍保留正确角色。
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_asset SET media_type='video' WHERE asset_id=:id"),
                             {'id': int(self.asset['id'])})
            await db.execute(text("UPDATE hf_stored_file SET mime_type='video/mp4' WHERE file_id="
                                  "(SELECT file_id FROM hf_asset_version WHERE version_id=:version)"),
                             {'version': int(self.asset['currentVersionId'])})
            await db.commit()
        video = await self.search(kind='asset')
        self.assertEqual(video.total, 1)
        self.assertEqual(video.rows[0]['allowedMediaRoles'], ['reference_video'])

    async def test_deleted_media_and_revoked_usage_remove_candidates(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        self.assertEqual((await self.search(pageSize=1)).total, 0)
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'asset:reference','project' FROM hf_project_role WHERE code='owner'"
                )
            )
            await db.execute(text("UPDATE hf_asset SET del_flag='2'"))
            await db.commit()
        self.assertEqual((await self.search()).total, 0)

    async def test_system_permissions_and_own_scope(self):
        limited = SimpleNamespace(
            user=self.owner.user, permissions=['project:read', 'generation:create', 'element:read', 'asset:read']
        )
        async with self.sessions() as db:
            self.assertEqual(
                (await ReferenceService.search(db, limited, ReferenceQuery(projectId=self.project_id))).total, 0
            )
        limited.permissions.remove('generation:create')
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ReferenceService.search(db, limited, ReferenceQuery(projectId=self.project_id))
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='asset:reference'")
            )
            await db.execute(text('UPDATE hf_asset SET create_user_id=9999'))
            await db.commit()
        self.assertEqual((await self.search()).total, 0)


    async def test_exact_element_filter_keeps_authorization_and_project_boundary(self):
        element_id = self.source['element']['id']
        result = await self.search(kind='element', elementId=element_id, pageSize=1)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]['id'], element_id)
        self.assertEqual(result.rows[0]['elementRevisionId'], self.source['currentRevision']['id'])
        self.assertEqual((await self.search(kind='element', elementId='9223372036854775807')).total, 0)
        async with self.sessions() as db:
            result = await ReferenceService.search(db, self.owner, ReferenceQuery(projectId=self.target_id, kind='element', elementId=element_id))
            self.assertEqual(result.total, 0)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        self.assertEqual((await self.search(kind='element', elementId=element_id)).total, 0)
        with self.assertRaises(ValueError):
            ReferenceQuery(projectId=self.project_id, kind='asset', elementId=element_id)

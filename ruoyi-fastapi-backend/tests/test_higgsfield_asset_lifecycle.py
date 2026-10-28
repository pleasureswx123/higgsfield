"""素材回收不丢版本、文件与引用身份；使用隔离 PostgreSQL schema。"""

import os
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import unittest
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.asset_vo import AssetAction, AssetCreate, AssetPatch, LibraryQuery
from module_higgsfield.service.asset_lifecycle_service import AssetLifecycleService
from module_higgsfield.service.asset_service import AssetService
from tests.test_higgsfield_assets import AssetDatabaseTests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class AssetLifecycleTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = AssetDatabaseTests.cleanup_schema
    create = AssetDatabaseTests.create
    new_upload = AssetDatabaseTests.new_upload
    send_part = AssetDatabaseTests.send_part
    ready_upload = AssetDatabaseTests.ready_upload

    async def asyncSetUp(self):
        await AssetDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'asset_lifecycle_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_10_asset_lifecycle.py',
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)
            self.assertEqual(
                await conn.scalar(
                    text("SELECT count(*) FROM hf_project_role_permission WHERE permission_code='asset:remove'")
                ),
                0,
            )
            await conn.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'asset:remove','own' FROM hf_project_role WHERE code='owner'"
                )
            )
        upload = await self.ready_upload()
        async with self.sessions() as db:
            result, _ = await AssetService.bind(
                db, self.owner, AssetCreate(projectId=self.project_id, uploadId=str(upload), name='原图'), str(uuid4())
            )
            self.asset = result['data']

    async def mutate(self, action, revision, key=None, **fields):
        payload = AssetPatch(revision=revision, **fields) if action == 'rename' else AssetAction(revision=revision)
        async with self.sessions() as db:
            return await AssetLifecycleService.mutate(
                db, self.owner, int(self.asset['id']), action, payload, key or str(uuid4())
            )

    async def test_rename_recycle_restore_and_replay(self):
        result, _ = await self.mutate('rename', '1', name='新名称')
        self.assertEqual(result['data']['name'], '新名称')
        with self.assertRaises(ServiceWarning):
            await self.mutate('delete', '1')
        key = str(uuid4())
        deleted, _ = await self.mutate('delete', '2', key)
        replay, repeated = await self.mutate('delete', '2', key)
        self.assertTrue(repeated)
        self.assertEqual(deleted, replay)
        async with self.sessions() as db:
            self.assertEqual(
                (await AssetService.library(db, self.owner, int(self.project_id), LibraryQuery())).total, 0
            )
            trash = await AssetLifecycleService.trash(db, self.owner, int(self.project_id), 1, 30)
            self.assertEqual(trash.total, 1)
            self.assertTrue(trash.rows[0]['canRestore'])
            for table in ('hf_stored_file', 'hf_asset_version', 'hf_folder_entry'):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 1)
        restore_key = str(uuid4())
        restored, _ = await self.mutate('restore', '3', restore_key)
        repeated_result, repeated = await self.mutate('restore', '3', restore_key)
        self.assertTrue(repeated)
        self.assertEqual(restored, repeated_result)
        self.assertEqual(restored['data']['currentVersionId'], self.asset['currentVersionId'])
        self.assertEqual(restored['data']['revision'], '4')
        async with self.sessions() as db:
            self.assertEqual(
                (await AssetService.library(db, self.owner, int(self.project_id), LibraryQuery())).total, 1
            )
            self.assertEqual(
                await db.scalar(text("SELECT state FROM hf_recycle_entry WHERE target_kind='asset'")), 'restored'
            )
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_asset')), 4)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:remove'"))
            await db.commit()
        # 已成功的幂等回放仍须重新鉴权，不因持有旧键绕过撤权。
        with self.assertRaises(PermissionException):
            await self.mutate('restore', '3', restore_key)

    async def test_expiry_and_own_scope(self):
        await self.mutate('delete', '1')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_recycle_entry SET deleted_time=now()-interval '32 days',restore_until=now()-interval '2 days' WHERE target_kind='asset'"
                )
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.mutate('restore', '2')
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_asset SET create_user_id=9999'))
            await db.commit()
        async with self.sessions() as db:
            self.assertEqual((await AssetLifecycleService.trash(db, self.owner, int(self.project_id), 1, 1)).total, 0)
        with self.assertRaises(PermissionException):
            await self.mutate('restore', '2')

    async def test_missing_original_folder_does_not_partially_restore(self):
        from module_higgsfield.service.folder_service import FolderService
        from module_higgsfield.entity.vo.folder_vo import FolderCreate

        async with self.sessions() as db:
            folder, _ = await FolderService.mutate(
                db,
                self.owner,
                'create',
                FolderCreate(name='原目录', folderKind='media').model_dump(by_alias=True),
                str(uuid4()),
                project_id=int(self.project_id),
            )
            folder_id = folder['data']['id']
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_folder_entry SET folder_id=:id'), {'id': int(folder_id)})
            await db.commit()
        await self.mutate('delete', '1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_folder SET del_flag='2' WHERE folder_id=:id"), {'id': int(folder_id)})
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.mutate('restore', '2')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT del_flag FROM hf_asset')), '2')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_recycle_entry')), 'active')

"""隔离schema验证目录真实迁移、层级并发和回收身份。"""

import asyncio
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.folder_vo import FolderCreate, FolderQuery
from module_higgsfield.service.folder_service import FolderService
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class FolderDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_04_folders.py'
            spec = importlib.util.spec_from_file_location('folder_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()

            await conn.run_sync(migrate)
            path = path.parent / '20261027_06_assets.py'
            spec = importlib.util.spec_from_file_location('folder_assets_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            await conn.run_sync(migrate)
            for permission in ('asset:read', 'folder:write'):
                await conn.execute(
                    text("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope)
                    SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner'
                    ON CONFLICT DO NOTHING"""),
                    {'permission': permission},
                )
        result, _ = await self.create()
        self.project_id = int(result['data']['id'])

    async def folder(self, name, parent=None):
        payload = FolderCreate(name=name, parentId=parent).model_dump(by_alias=True)
        async with self.sessions() as db:
            result, _ = await FolderService.mutate(
                db, self.owner, 'create', payload, str(uuid4()), project_id=self.project_id
            )
            return result['data']

    async def action(self, folder, action, payload=None, key=None, user=None):
        async with self.sessions() as db:
            return await FolderService.mutate(
                db,
                user or self.owner,
                action,
                {'revision': folder['revision'], **(payload or {})},
                key or str(uuid4()),
                folder_id=int(folder['id']),
            )

    async def test_tree_delete_restore_and_copy_replay(self):
        parent = await self.folder('父目录')
        child = await self.folder('子目录', parent['id'])
        key = str(uuid4())
        copied, replayed = await self.action(parent, 'copy', {'targetParentId': None}, key)
        repeated, replayed = await self.action(parent, 'copy', {'targetParentId': None}, key)
        self.assertTrue(replayed)
        self.assertEqual(copied, repeated)
        async with self.sessions() as db:
            listing = await FolderService.list(
                db, self.owner, self.project_id, FolderQuery(parentId=copied['data']['id'])
            )
            self.assertEqual(len(listing.rows), 1)
            self.assertNotEqual(listing.rows[0]['id'], child['id'])
        deleted, _ = await self.action(parent, 'delete')
        restore_key = str(uuid4())
        restored, _ = await self.action(deleted['data'], 'restore', key=restore_key)
        repeated_result, replayed = await self.action(deleted['data'], 'restore', key=restore_key)
        self.assertTrue(replayed)
        self.assertEqual(restored, repeated_result)
        self.assertEqual(restored['data']['id'], parent['id'])
        async with self.sessions() as db:
            listing = await FolderService.list(db, self.owner, self.project_id, FolderQuery())
            self.assertIn(child['id'], [row['id'] for row in listing.rows])
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='folder:write'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.action(deleted['data'], 'restore', key=restore_key)

    async def test_concurrent_moves_cannot_create_cycle(self):
        left, right = await self.folder('左'), await self.folder('右')
        results = await asyncio.gather(
            self.action(left, 'move', {'parentId': right['id']}),
            self.action(right, 'move', {'parentId': left['id']}),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, ServiceWarning) for result in results), 1)

    async def test_permission_revision_and_normalized_name(self):
        folder = await self.folder('Ａbc')
        with self.assertRaises(ServiceWarning):
            await self.folder('abc')
        with self.assertRaises(ServiceWarning):
            await self.action(folder, 'edit', {'name': '越权'}, user=self.other)
        await self.action(folder, 'edit', {'name': '新名称'})
        with self.assertRaises(ServiceWarning):
            await self.action(folder, 'delete')
        async with self.sessions() as db:
            current = await FolderService.detail(db, self.owner, int(folder['id']))
            result, replayed = await FolderService.mutate(
                db,
                self.owner,
                'edit',
                {'revision': current['folder']['revision'], 'name': '不携带幂等键'},
                None,
                folder_id=int(folder['id']),
            )
            self.assertFalse(replayed)
            self.assertEqual(result['data']['name'], '不携带幂等键')

    async def test_delete_collision_is_atomic(self):
        parent = await self.folder('父')
        await self.folder('同名', parent['id'])
        await self.folder('同名')
        with self.assertRaises(ServiceWarning):
            await self.action(parent, 'delete')
        async with self.sessions() as db:
            listing = await FolderService.list(db, self.owner, self.project_id, FolderQuery())
            self.assertIn(parent['id'], [row['id'] for row in listing.rows])

    async def test_same_name_parent_child_and_authorized_path(self):
        child = await self.folder('同名')
        parent = await self.folder('父')
        moved, _ = await self.action(child, 'move', {'parentId': parent['id']})
        renamed, _ = await self.action(parent, 'edit', {'name': '同名'})
        async with self.sessions() as db:
            detail = await FolderService.detail(db, self.owner, int(child['id']))
            self.assertEqual([item['id'] for item in detail['ancestors']], [parent['id']])
        await self.action(renamed['data'], 'delete')
        async with self.sessions() as db:
            detail = await FolderService.detail(db, self.owner, int(child['id']))
            self.assertEqual(detail['ancestors'], [])
            self.assertNotEqual(detail['folder']['revision'], moved['data']['revision'])

    async def test_expired_restore_and_migration_metadata(self):
        folder = await self.folder('过期目录')
        deleted, _ = await self.action(folder, 'delete')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_recycle_entry SET deleted_time=now()-interval '40 days', "
                    "restore_until=now()-interval '10 days'"
                )
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.action(deleted['data'], 'restore')
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(
                    text("""SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname=:schema AND c.contype='f'"""),
                    {'schema': self.schema},
                ),
                0,
            )
            missing = await db.scalar(
                text("""SELECT count(*) FROM pg_attribute a
                JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname=:schema AND c.relname IN ('hf_folder','hf_recycle_entry')
                AND a.attnum>0 AND NOT a.attisdropped AND col_description(c.oid,a.attnum) IS NULL"""),
                {'schema': self.schema},
            )
            self.assertEqual(missing, 0)

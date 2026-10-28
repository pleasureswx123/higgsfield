"""元素事务、幂等、状态审计与目录集成的隔离数据库测试。"""

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.entity.vo.element_vo import (
    ElementCreate,
    ElementLabel,
    ElementRevisionAction,
    ElementSave,
    ElementQuery,
    PropertyDefinitionCreate,
    PropertyDefinitionFields,
)
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.entity.vo.folder_vo import FolderCreate
from tests import test_higgsfield_elements as elements


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class ElementServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = elements.ElementDatabaseTests.cleanup_schema
    create = elements.ElementDatabaseTests.create

    async def asyncSetUp(self):
        await elements.ElementDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_08_review_events.py'
            spec = importlib.util.spec_from_file_location('review_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()

            await conn.run_sync(migrate)
            for permission in (
                'element:read',
                'element:create',
                'element:edit',
                'element:copy',
                'element:configure',
                'element:remove',
                'content:review',
            ):
                await conn.execute(
                    text("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope)
                    SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"""),
                    {'permission': permission},
                )

    async def make_element(self, **changes):
        fields = {'projectId': self.project_id, 'name': '主角', 'alias': 'hero', 'category': 'character'}
        fields.update(changes)
        async with self.sessions() as db:
            result, _ = await ElementService.create(db, self.owner, ElementCreate(**fields), str(uuid4()))
            return result['data']

    async def test_recycle_restore_preserves_identity_and_replay(self):
        created = await self.make_element()
        element_id = int(created['element']['id'])
        key = str(uuid4())
        payload = ElementRevisionAction(revision='1')
        async with self.sessions() as db:
            removed, _ = await ElementService.lifecycle(db, self.owner, element_id, 'delete', payload, key)
        async with self.sessions() as db:
            replay, repeated = await ElementService.lifecycle(db, self.owner, element_id, 'delete', payload, key)
            self.assertTrue(repeated)
            self.assertEqual(replay, removed)
            trash = await ElementService.trash(db, self.owner, int(self.project_id), 1, 30)
            self.assertEqual(trash.total, 1)
            self.assertEqual(trash.rows[0]['revision'], '2')
            self.assertTrue(trash.rows[0]['canRestore'])
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ElementService.detail(db, self.owner, element_id)
        async with self.sessions() as db:
            restored, _ = await ElementService.lifecycle(
                db, self.owner, element_id, 'restore', ElementRevisionAction(revision='2'), str(uuid4())
            )
            self.assertEqual(restored['data']['id'], str(element_id))
            self.assertEqual(restored['data']['currentRevisionId'], created['currentRevision']['id'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_recycle_entry WHERE state='restored'")), 1)

    async def test_restore_expiry_and_missing_parent(self):
        async with self.sessions() as db:
            folder, _ = await FolderService.mutate(
                db,
                self.owner,
                'create',
                FolderCreate(name='原目录', folderKind='element').model_dump(by_alias=True),
                str(uuid4()),
                project_id=int(self.project_id),
            )
        created = await self.make_element(folderId=folder['data']['id'])
        element_id = int(created['element']['id'])
        async with self.sessions() as db:
            await ElementService.lifecycle(db, self.owner, element_id, 'delete', ElementRevisionAction(revision='1'))
        async with self.sessions() as db:
            await FolderService.mutate(
                db,
                self.owner,
                'delete',
                {'revision': '1', 'mode': 'moveEntriesToParent'},
                str(uuid4()),
                folder_id=int(folder['data']['id']),
            )
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning) as problem:
                await ElementService.lifecycle(
                    db, self.owner, element_id, 'restore', ElementRevisionAction(revision='2'), str(uuid4())
                )
            self.assertEqual(problem.exception.data['errorCode'], 'RESTORE_PARENT_UNAVAILABLE')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_recycle_entry SET deleted_time=CURRENT_TIMESTAMP-INTERVAL '32 days', restore_until=CURRENT_TIMESTAMP-INTERVAL '2 days' WHERE target_kind='element'"
                )
            )
            await db.commit()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning) as problem:
                await ElementService.lifecycle(
                    db, self.owner, element_id, 'restore', ElementRevisionAction(revision='2'), str(uuid4())
                )
            self.assertEqual(problem.exception.data['errorCode'], 'RESTORE_EXPIRED')

    async def test_own_recycle_scope_filters_before_pagination(self):
        own = await self.make_element(alias='own')
        other = await self.make_element(alias='other')
        async with self.sessions() as db:
            await db.execute(
                text('UPDATE hf_element SET create_user_id=2 WHERE element_id=:id'), {'id': int(other['element']['id'])}
            )
            await db.commit()
        for element in (own['element'], other['element']):
            async with self.sessions() as db:
                await ElementService.lifecycle(
                    db, self.owner, int(element['id']), 'delete', ElementRevisionAction(revision='1')
                )
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='element:remove'")
            )
            await db.commit()
        async with self.sessions() as db:
            page = await ElementService.trash(db, self.owner, int(self.project_id), 1, 1)
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['targetId'], own['element']['id'])
            self.assertFalse(page.has_next)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ElementService.lifecycle(
                    db,
                    self.owner,
                    int(other['element']['id']),
                    'restore',
                    ElementRevisionAction(revision='2'),
                    str(uuid4()),
                )

    async def test_atomic_save_replay_revision_and_review(self):
        created = await self.make_element()
        element = created['element']
        payload = ElementSave(
            revision=element['revision'],
            name='主角新名',
            alias='hero',
            category='character',
            description='新描述',
            workStatus='approved',
            label='审核稿',
        )
        key = str(uuid4())
        async with self.sessions() as db:
            saved, _ = await ElementService.mutate(db, self.owner, int(element['id']), 'save', payload, key)
        async with self.sessions() as db:
            replay, was_replayed = await ElementService.mutate(db, self.owner, int(element['id']), 'save', payload, key)
            self.assertTrue(was_replayed)
            self.assertEqual(saved, replay)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_review_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 2)
            original = await ElementDao.revision(db, int(created['currentRevision']['id']))
            self.assertEqual(original.description, '')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ElementService.mutate(db, self.owner, int(element['id']), 'save', payload, str(uuid4()))
        payload.revision = saved['data']['element']['revision']
        payload.label = '只改展示标签'
        async with self.sessions() as db:
            renamed, _ = await ElementService.mutate(db, self.owner, int(element['id']), 'save', payload, str(uuid4()))
            self.assertEqual(renamed['data']['currentRevision']['id'], saved['data']['currentRevision']['id'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 2)

    async def test_label_cas_and_stale_full_save(self):
        created = await self.make_element()
        element, revision = created['element'], created['currentRevision']
        async with self.sessions() as db:
            result, _ = await ElementService.label(
                db, self.owner, int(revision['id']), ElementLabel(revision=revision['labelRevision'], label='新标签')
            )
            self.assertEqual(result['data']['revision'], '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 1)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ElementService.label(
                    db, self.owner, int(revision['id']), ElementLabel(revision='1', label='旧标签')
                )
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ElementService.mutate(
                    db,
                    self.owner,
                    int(element['id']),
                    'save',
                    ElementSave(revision='1', name='主角', alias='hero', category='character'),
                    str(uuid4()),
                )

    async def test_failure_rolls_back_and_list_is_scoped(self):
        # mine聚合现在读取真实收藏表，隔离测试须执行对应迁移。
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_67_favorites.py'
        spec = importlib.util.spec_from_file_location('mine_favorites_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:
            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()
            await conn.run_sync(migrate)
        created = await self.make_element()
        element = created['element']
        restricted = SimpleNamespace(user=self.owner.user, permissions=['element:edit', 'element:read', 'project:read'])
        payload = ElementSave(revision='1', name='不能保存的名字', alias='hero', category='prop', workStatus='approved')
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ElementService.mutate(db, restricted, int(element['id']), 'save', payload, str(uuid4()))
        async with self.sessions() as db:
            detail = await ElementService.detail(db, self.owner, int(element['id']))
            self.assertEqual(detail['element']['name'], '主角')
            self.assertEqual(detail['element']['revision'], '1')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_review_event')), 0)
            page = await ElementService.listing(db, self.owner, ElementQuery(projectId=self.project_id))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['projectId'], str(self.project_id))
            self.assertTrue(page.rows[0]['projectName'])
            self.assertEqual(page.rows[0]['revisionNo'], 1)
            self.assertEqual(page.rows[0]['description'], created['currentRevision']['description'])
            mine = await ElementService.listing(db, self.owner, ElementQuery(scope='mine'))
            self.assertEqual([row['id'] for row in mine.rows], [element['id']])
            none = await ElementService.listing(
                db, self.owner, ElementQuery(projectId=self.project_id, statusGroup='active')
            )
            self.assertEqual(none.total, 0)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
        async with self.sessions() as db:
            page = await ElementService.listing(db, self.owner, ElementQuery(scope='mine'))
            self.assertEqual(page.total, 0)

    async def test_property_versions_and_element_folder_copy_delete(self):
        async with self.sessions() as db:
            first, _ = await ElementService.write_definition(
                db,
                self.owner,
                PropertyDefinitionCreate(propertyKey='color', name='颜色', valueType='multi_select', options=['红']),
                str(uuid4()),
                project_id=int(self.project_id),
            )
        async with self.sessions() as db:
            second, _ = await ElementService.write_definition(
                db,
                self.owner,
                PropertyDefinitionFields(name='颜色新版', valueType='multi_select', options=['蓝']),
                str(uuid4()),
                definition_id=int(first['data']['id']),
            )
            self.assertEqual(second['data']['versionNo'], 2)
            definitions = await ElementService.definitions(db, self.owner, int(self.project_id), 1, 30)
            self.assertEqual(definitions.total, 1)
            self.assertEqual(definitions.rows[0]['options'], ['蓝'])
            original = await ElementDao.definition(db, int(first['data']['id']))
            self.assertEqual(original.options, ['红'])
        async with self.sessions() as db:
            folder, _ = await FolderService.mutate(
                db,
                self.owner,
                'create',
                FolderCreate(name='角色', folderKind='element').model_dump(by_alias=True),
                str(uuid4()),
                project_id=int(self.project_id),
            )
        created = await self.make_element(folderId=folder['data']['id'])
        async with self.sessions() as db:
            await FolderService.mutate(
                db,
                self.owner,
                'copy',
                {'revision': '1', 'name': '角色副本', 'targetParentId': None},
                str(uuid4()),
                folder_id=int(folder['data']['id']),
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 2)
        async with self.sessions() as db:
            await FolderService.mutate(
                db,
                self.owner,
                'delete',
                {'revision': '1', 'mode': 'moveEntriesToParent'},
                str(uuid4()),
                folder_id=int(folder['data']['id']),
            )
        async with self.sessions() as db:
            element = await ElementDao.element(db, int(created['element']['id']))
            self.assertIsNone(element.folder_id)
            self.assertEqual(element.revision, 2)

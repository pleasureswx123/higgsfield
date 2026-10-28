"""在独立 PostgreSQL schema 中验证真实迁移、事务和成员隔离。"""

import asyncio
import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.database import build_async_sqlalchemy_database_url
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.entity.vo.project_vo import ProjectCreate, ProjectQuery
from module_higgsfield.entity.vo.project_workspace_vo import BriefUpdate, MemberQuery
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.project_workspace_service import WorkspaceService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class ProjectDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'hf_project_test_' + uuid4().hex
        self.admin = create_async_engine(build_async_sqlalchemy_database_url())
        async with self.admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA {self.schema}'))
        self.engine = create_async_engine(
            build_async_sqlalchemy_database_url(),
            connect_args={'server_settings': {'search_path': self.schema}},
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.addAsyncCleanup(self.cleanup_schema)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    'CREATE TABLE sys_user (user_id bigint PRIMARY KEY, status char(1), '
                    'del_flag char(1), user_name text, nick_name text)'
                )
            )
            await conn.execute(
                text("INSERT INTO sys_user VALUES (1,'0','0','owner','负责人'),(2,'0','0','other','成员')")
            )
            await conn.execute(
                text("""CREATE TABLE sys_menu (
                menu_id bigserial PRIMARY KEY, menu_name text, parent_id bigint,
                order_num int, path text, menu_type text, visible text, status text,
                perms text, create_by text, create_time timestamptz)""")
            )
            migration = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_01_projects.py'
            spec = importlib.util.spec_from_file_location('project_migration_test', migration)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()

            await conn.run_sync(migrate)
            workspace_path = migration.parent / '20261027_03_project_workspace.py'
            workspace_spec = importlib.util.spec_from_file_location('workspace_migration_test', workspace_path)
            workspace = importlib.util.module_from_spec(workspace_spec)
            workspace_spec.loader.exec_module(workspace)

            def migrate_workspace(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    workspace.upgrade()

            await conn.run_sync(migrate_workspace)
            routing_spec = importlib.util.spec_from_file_location(
                'routing_migration_test', migration.parent / '20261027_21_routing.py'
            )
            routing = importlib.util.module_from_spec(routing_spec)
            routing_spec.loader.exec_module(routing)

            def migrate_routing(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    routing.upgrade()

            await conn.run_sync(migrate_routing)
            preference_spec = importlib.util.spec_from_file_location(
                'preference_migration_test', migration.parent / '20261028_72_project_preferences.py'
            )
            preference = importlib.util.module_from_spec(preference_spec)
            preference_spec.loader.exec_module(preference)

            def migrate_preference(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    preference.upgrade()

            await conn.run_sync(migrate_preference)
            view_spec = importlib.util.spec_from_file_location(
                'view_migration_test', migration.parent / '20261028_73_view_preferences.py'
            )
            view = importlib.util.module_from_spec(view_spec)
            view_spec.loader.exec_module(view)

            def migrate_view(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    view.upgrade()

            await conn.run_sync(migrate_view)
        self.owner = SimpleNamespace(permissions=['*:*:*'], user=SimpleNamespace(user_id=1, user_name='测试负责人'))
        self.other = SimpleNamespace(permissions=['*:*:*'], user=SimpleNamespace(user_id=2, user_name='测试其他人'))

    async def cleanup_schema(self):
        await self.engine.dispose()
        async with self.admin.begin() as conn:
            # schema 仅由本测试生成，绝不清理 public 中的数据。
            await conn.execute(text(f'DROP SCHEMA {self.schema} CASCADE'))
        await self.admin.dispose()

    async def create(self, name='测试项目', key=None):
        async with self.sessions() as db:
            return await ProjectService.create_project(db, self.owner, ProjectCreate(name=name), key or str(uuid4()))

    async def test_creation_replay_and_atomic_relations(self):
        key = str(uuid4())
        original, replayed = await self.create(key=key)
        self.assertFalse(replayed)
        repeated, replayed = await self.create(key=key)
        self.assertTrue(replayed)
        self.assertEqual(original, repeated)
        self.assertIsInstance(original['data']['id'], str)
        async with self.sessions() as db:
            for table in (
                'hf_project',
                'hf_project_member',
                'hf_asset_space',
                'hf_project_brief',
                'hf_api_idempotency_record',
            ):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 1)
        with self.assertRaises(ServiceWarning):
            await self.create(name='不同内容', key=key)
        await self.create()

    async def test_scope_and_revocation_apply_to_replay(self):
        key = str(uuid4())
        result, _ = await self.create(key=key)
        project_id = int(result['data']['id'])
        async with self.sessions() as db:
            page = await ProjectService.list_projects(db, self.other, ProjectQuery())
            self.assertEqual(page.total, 0)
            with self.assertRaises(ServiceWarning):
                await ProjectService.get_project(db, self.other, project_id)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.create(key=key)

    async def test_failure_rolls_back_every_write(self):
        with patch.object(ProjectDao, 'save_idempotency', AsyncMock(side_effect=RuntimeError('模拟写入失败'))):
            with self.assertRaises(RuntimeError):
                await self.create()
        async with self.sessions() as db:
            for table in ('hf_project', 'hf_project_member', 'hf_asset_space', 'hf_project_brief'):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 0)

    async def test_literal_search_and_stable_pagination(self):
        await self.create(name='100%项目')
        await self.create(name='普通项目')
        async with self.sessions() as db:
            result = await ProjectService.list_projects(db, self.owner, ProjectQuery(q='%'))
            self.assertEqual(result.total, 1)
            first = await ProjectService.list_projects(db, self.owner, ProjectQuery(pageSize=1))
            second = await ProjectService.list_projects(db, self.owner, ProjectQuery(pageSize=1, pageNum=2))
            self.assertNotEqual(first.rows[0].id, second.rows[0].id)

    async def test_concurrent_request_lock(self):
        key = str(uuid4())
        async with self.sessions() as db:
            self.assertTrue(await ProjectDao.acquire_creation_lock(db, 1, key))
            with self.assertRaises(ServiceWarning):
                await self.create(key=key)
            await db.rollback()
        await self.create(key=key)

    async def workspace_fixture(self):
        result, _ = await self.create()
        project_id = int(result['data']['id'])
        async with self.sessions() as db:
            roles = (await WorkspaceService.roles(db, self.owner, project_id))['items']
        return project_id, {role['code']: role['id'] for role in roles}

    async def mutate(self, project_id, action, payload, user=None, user_id=None, key=None):
        async with self.sessions() as db:
            return await WorkspaceService.mutate(
                db, user or self.owner, project_id, action, payload, key or str(uuid4()), user_id
            )

    async def test_brief_revision_idempotency_and_validation(self):
        project_id, _ = await self.workspace_fixture()
        body = {
            'schemaVersion': 1,
            'type': 'doc',
            'content': [
                {'type': 'paragraph', 'content': [{'type': 'text', 'text': '真实简报', 'marks': [{'type': 'bold'}]}]}
            ],
        }
        payload = BriefUpdate(revision='1', body=body).model_dump(by_alias=True)
        key = str(uuid4())
        first, _ = await self.mutate(project_id, 'brief', payload, key=key)
        replay, flag = await self.mutate(project_id, 'brief', payload, key=key)
        self.assertTrue(flag)
        self.assertEqual(first, replay)
        self.assertEqual(first['data']['revision'], '2')
        with self.assertRaises(ServiceWarning):
            await self.mutate(project_id, 'brief', payload)
        for content in [
            [{'type': 'script'}],
            [
                {
                    'type': 'paragraph',
                    'content': [
                        {'type': 'text', 'text': '恶意链接', 'marks': [{'type': 'link', 'href': 'javascript:alert(1)'}]}
                    ],
                }
            ],
        ]:
            with self.assertRaises(ValidationError):
                BriefUpdate(revision='2', body={**body, 'content': content})

    async def test_members_roles_removal_and_restoration(self):
        project_id, roles = await self.workspace_fixture()
        key = str(uuid4())
        payload = {'userId': '2', 'roleId': roles['viewer']}
        result, _ = await self.mutate(project_id, 'add', payload, key=key)
        replay, replayed = await self.mutate(project_id, 'add', payload, key=key)
        self.assertTrue(replayed)
        self.assertEqual(result, replay)
        async with self.sessions() as db:
            page = await WorkspaceService.list_members(db, self.other, project_id, MemberQuery())
            self.assertEqual(page.total, 2)
            self.assertNotIn(
                'member:manage', (await WorkspaceService.get_brief(db, self.other, project_id))['allowedActions']
            )
        with self.assertRaises(PermissionException):
            await self.mutate(
                project_id, 'role', {'revision': '1', 'roleId': roles['owner']}, user=self.other, user_id=2
            )
        await self.mutate(project_id, 'role', {'revision': '1', 'roleId': roles['producer']}, user_id=2)
        with self.assertRaises(ServiceWarning):
            await self.mutate(project_id, 'remove', {'revision': '1'}, user_id=2)
        await self.mutate(project_id, 'remove', {'revision': '2'}, user_id=2)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await WorkspaceService.get_brief(db, self.other, project_id)
        restored, _ = await self.mutate(project_id, 'add', payload)
        self.assertEqual(restored['data']['revision'], '4')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_member WHERE user_id=2')), 1)

    async def test_last_owner_and_concurrent_removal(self):
        project_id, roles = await self.workspace_fixture()
        with self.assertRaises(ServiceWarning):
            await self.mutate(project_id, 'remove', {'revision': '1'}, user_id=1)
        with self.assertRaises(ServiceWarning):
            await self.mutate(project_id, 'role', {'revision': '1', 'roleId': roles['viewer']}, user_id=1)
        await self.mutate(project_id, 'add', {'userId': '2', 'roleId': roles['owner']})
        results = await asyncio.gather(
            self.mutate(project_id, 'remove', {'revision': '1'}, user_id=2),
            self.mutate(project_id, 'remove', {'revision': '1'}, user=self.other, user_id=1),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, Exception) for result in results), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_project_member WHERE status='0'")), 1)

    async def test_project_state_and_system_permission_gate(self):
        project_id, _ = await self.workspace_fixture()
        restricted = SimpleNamespace(permissions=['project:read'], user=self.owner.user)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await WorkspaceService.list_members(db, restricted, project_id, MemberQuery())
            await db.execute(text("UPDATE hf_project SET status='1'"))
            await db.commit()
        async with self.sessions() as db:
            with patch.object(
                WorkspaceService,
                'authorize',
                return_value=(
                    SimpleNamespace(status='1'),
                    'owner',
                    {'project:read', 'asset:upload', 'asset:create', 'asset:edit', 'asset:read'},
                ),
            ):
                result = await WorkspaceService.get_brief(db, self.owner, project_id)
                self.assertEqual(result['allowedActions'], ['asset:read', 'project:read'])
        with self.assertRaises(ServiceWarning):
            await self.mutate(
                project_id, 'brief', {'revision': '1', 'body': {'schemaVersion': 1, 'type': 'doc', 'content': []}}
            )

    async def test_workspace_write_failure_rolls_back(self):
        project_id, roles = await self.workspace_fixture()
        with patch.object(ProjectDao, 'save_idempotency', AsyncMock(side_effect=RuntimeError('模拟写入失败'))):
            with self.assertRaises(RuntimeError):
                await self.mutate(project_id, 'add', {'userId': '2', 'roleId': roles['viewer']})
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_member')), 1)

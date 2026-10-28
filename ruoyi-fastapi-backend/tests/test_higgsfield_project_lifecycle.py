"""制作端生命周期真实迁移、成员权限、并发修订及审计回滚验证。"""
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.project_vo import ProjectArchive, ProjectRestore, ProjectUpdate, ProjectPause
from module_higgsfield.service.project_lifecycle_service import ProjectLifecycleService
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from tests import test_higgsfield_projects as projects


class LifecycleInputTests(unittest.TestCase):
    def test_pause_requires_reason(self):
        for reason in ('', ' ', '\t'):
            with self.assertRaises(ValidationError):
                ProjectPause(revision='1', reason=reason)
        self.assertEqual(ProjectPause(revision='1', reason=' 维护 ').reason, '维护')

    def test_project_name_uses_creation_validation(self):
        self.assertEqual(ProjectUpdate(revision='1', name=' 新名称 ').name, '新名称')
        for name in (' ', '名称\n控制符', '字' * 201):
            with self.assertRaises(ValidationError):
                ProjectUpdate(revision='1', name=name)
        with self.assertRaises(ValidationError):
            ProjectUpdate(revision='1')

    def test_archive_requires_reason_and_restore_requires_revision(self):
        for reason in ('', '   ', '\t'):
            with self.assertRaises(ValidationError):
                ProjectArchive(revision='1', reason=reason)
        self.assertEqual(ProjectArchive(revision='1', reason=' 完结 ').reason, '完结')
        self.assertEqual(ProjectRestore(revision='1').reason, '')
        with self.assertRaises(ValidationError):
            ProjectRestore(revision='0')


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            for filename in ('20261027_16_audit.py', '20261028_74_project_lifecycle.py', '20261028_75_project_manage.py'):
                spec = importlib.util.spec_from_file_location('lifecycle_migration',
                    Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
        result, _ = await self.create()
        self.identity = int(result['data']['id'])

    async def change(self, action, revision, *, key=None, user=None, reason='项目完结'):
        model = {'archive': ProjectArchive, 'pause': ProjectPause}.get(action, ProjectRestore)
        payload = model(revision=str(revision), reason=reason)
        async with self.sessions() as db:
            return await ProjectLifecycleService.change(db, user or self.owner, self.identity,
                action, payload, key or str(uuid4()))

    async def rename(self, name, revision, key=None, user=None):
        async with self.sessions() as db:
            return await ProjectLifecycleService.change(db, user or self.owner, self.identity, 'rename',
                ProjectUpdate(name=name, revision=str(revision)), key or str(uuid4()))

    async def test_rename_identity_audit_replay_and_readonly(self):
        key = str(uuid4())
        renamed, replayed = await self.rename(' 新名称 ', 1, key)
        self.assertFalse(replayed)
        self.assertEqual(renamed['data']['name'], '新名称')
        self.assertEqual(renamed['data']['id'], str(self.identity))
        repeated, replayed = await self.rename('新名称', 1, key)
        self.assertTrue(replayed)
        self.assertEqual(repeated, renamed)
        with self.assertRaises(ServiceWarning):
            await self.rename('覆盖修改', 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT http_method FROM hf_api_idempotency_record WHERE normalized_path=:path'),
                {'path': f'/projects/{self.identity}'}), 'PATCH')
            evidence = await db.scalar(text('SELECT before_after FROM hf_audit_log'))
            self.assertEqual(evidence['before']['name'], '测试项目')
            self.assertEqual(evidence['after']['name'], '新名称')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset_space')), 1)
        await self.change('archive', 2)
        from module_higgsfield.service.project_workspace_service import WorkspaceService
        async with self.sessions() as db:
            brief = await WorkspaceService.get_brief(db, self.owner, self.identity)
            self.assertNotIn('project:manage', brief['allowedActions'])
            self.assertIn('project:archive', brief['allowedActions'])
        with self.assertRaises(ServiceWarning):
            await self.rename('归档不能编辑', 3)

    async def test_rename_scope_and_atomic_rollback(self):
        with self.assertRaises(ServiceWarning):
            await self.rename('无关用户', 1, user=self.other)
        self.owner.permissions = ['project:edit']
        with self.assertRaises(PermissionException):
            await self.rename('仅简报权限', 1)
        self.owner.permissions = ['project:manage']
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('故障注入'))):
            with self.assertRaises(RuntimeError):
                await self.rename('应回滚', 1)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT project_name,revision FROM hf_project'))).one(), ('测试项目', 1))

    async def test_concurrent_rename_preserves_single_revision(self):
        import asyncio
        results = await asyncio.gather(self.rename('甲', 1), self.rename('乙', 1), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, tuple) for item in results), 1, results)
        self.assertEqual(sum(isinstance(item, ServiceWarning) for item in results), 1, results)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_project')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

    async def test_transitions_replay_and_revocation(self):
        key = str(uuid4())
        with self.assertRaises(ServiceWarning):
            await self.change('archive', 1, user=self.other)
        result, repeated = await self.change('archive', 1, key=key)
        self.assertFalse(repeated)
        self.assertEqual(result['data']['status'], 'archived')
        self.assertIsNotNone(result['data']['archivedAt'])
        replay, repeated = await self.change('archive', 1, key=key)
        self.assertTrue(repeated)
        self.assertEqual(replay, result)
        with self.assertRaises(ServiceWarning):
            await self.change('archive', 1, key=key, reason='不同请求')
        with self.assertRaises(ServiceWarning):
            await self.change('restore', 1)
        restored, _ = await self.change('restore', 2)
        self.assertEqual(restored['data']['status'], 'active')
        self.assertIsNone(restored['data']['archivedAt'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 2)
            await db.execute(text("UPDATE hf_project_member SET status='1' WHERE user_id=1"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.change('archive', 1, key=key)

    async def test_function_permission_and_audit_failure(self):
        self.owner.permissions = ['project:read']
        with self.assertRaises(PermissionException):
            await self.change('archive', 1)
        self.owner.permissions = ['project:archive']
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('故障注入'))):
            with self.assertRaises(RuntimeError):
                await self.change('archive', 1)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT status,revision,archived_time FROM hf_project'))).one(), ('0', 1, None))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_api_idempotency_record')), 1)
        await self.change('archive', 1)

    async def test_concurrent_archive_has_one_transition(self):
        import asyncio
        results = await asyncio.gather(self.change('archive', 1), self.change('archive', 1), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, tuple) for item in results), 1, results)
        self.assertEqual(sum(isinstance(item, ServiceWarning) for item in results), 1, results)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_project')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

    async def test_pause_resume_replay_and_readonly_authorization(self):
        from module_higgsfield.service.project_workspace_service import WorkspaceService
        key = str(uuid4())
        result, repeated = await self.change('pause', 1, key=key)
        self.assertEqual(result['data']['status'], 'paused')
        self.assertIsNone(result['data']['archivedAt'])
        self.assertFalse(repeated)
        self.assertTrue((await self.change('pause', 1, key=key))[1])
        async with self.sessions() as db:
            brief = await WorkspaceService.get_brief(db, self.owner, self.identity)
            self.assertIn('project:manage', brief['allowedActions'])
            self.assertNotIn('project:edit', brief['allowedActions'])
            with self.assertRaises(ServiceWarning):
                await WorkspaceService.authorize(db, self.owner, self.identity, 'project:edit', write=True)
        with self.assertRaises(ServiceWarning):
            await self.rename('暂停时改名', 2)
        with self.assertRaises(ServiceWarning):
            await self.change('pause', 2)
        resumed, _ = await self.change('resume', 2, reason='')
        self.assertEqual(resumed['data']['status'], 'active')
        async with self.sessions() as db:
            await WorkspaceService.authorize(db, self.owner, self.identity, 'project:edit', write=True)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 2)
        with self.assertRaises(ServiceWarning):
            await self.change('resume', 3)
        await self.change('archive', 3)
        with self.assertRaises(ServiceWarning):
            await self.change('resume', 4)

    async def test_pause_requires_manage_permission_and_rolls_back(self):
        self.owner.permissions = ['project:archive']
        with self.assertRaises(PermissionException):
            await self.change('pause', 1)
        self.owner.permissions = ['project:manage']
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计故障'))):
            with self.assertRaises(RuntimeError):
                await self.change('pause', 1)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT status,revision FROM hf_project'))).one(), ('0', 1))

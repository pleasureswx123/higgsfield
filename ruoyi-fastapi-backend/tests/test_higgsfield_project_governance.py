"""项目治理复用真实管理范围，状态、审计与幂等原子提交。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import ServiceWarning, PermissionException
from tests.test_higgsfield_admin_scope import AdminScopeTests
from module_higgsfield.entity.vo.project_governance_vo import ProjectGovernanceAction
from module_higgsfield.service.project_governance_service import ProjectGovernanceService

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要启用隔离数据库测试')
class GovernanceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = AdminScopeTests.cleanup_schema
    create = AdminScopeTests.create
    scope = AdminScopeTests.scope

    async def asyncSetUp(self):
        await AdminScopeTests.asyncSetUp(self)
        self.actor.permissions = ['project:govern']
        self.actor.user.user_name = '治理用户'
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE sys_menu SET perms='project:govern' WHERE menu_id=9001"))
            for name in ['20261027_16_audit.py', '20261028_48_project_governance.py']:
                spec = importlib.util.spec_from_file_location('governance_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)

    async def change(self, action, revision, key=None):
        async with self.sessions() as db:
            return await ProjectGovernanceService.change(db, self.actor, self.project_id, ProjectGovernanceAction(action=action, revision=str(revision), reason='治理测试'), key or str(uuid4()))

    async def test_scope_transitions_and_idempotent_audit(self):
        with self.assertRaises(ServiceWarning):
            await self.change('pause', 1)
        await self.scope('1')
        key = str(uuid4())
        result, replayed = await self.change('pause', 1, key)
        self.assertEqual(result['data']['status'], 'paused')
        self.assertFalse(replayed)
        _, replayed = await self.change('pause', 1, key)
        self.assertTrue(replayed)
        with self.assertRaises(ServiceWarning):
            await self.change('pause', 2)
        await self.change('resume', 2)
        await self.change('archive', 3)
        async with self.sessions() as db:
            self.assertIsNotNone(await db.scalar(text('SELECT archived_time FROM hf_project')))
        restored, _ = await self.change('restore', 4)
        self.assertEqual(restored['data']['status'], 'active')
        self.assertNotIn('brief', restored['data'])
        async with self.sessions() as db:
            self.assertIsNone(await db.scalar(text('SELECT archived_time FROM hf_project')))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 4)
            await db.execute(text('DELETE FROM sys_role_menu WHERE menu_id=9001')); await db.commit()
        with self.assertRaises(PermissionException):
            await self.change('pause', 1, key)

    async def test_audit_failure_rolls_back_status(self):
        from unittest.mock import AsyncMock, patch
        from module_higgsfield.dao.price_source_dao import PriceSourceDao
        await self.scope('1')
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计写入失败'))):
            with self.assertRaises(RuntimeError):
                await self.change('archive', 1)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT status,revision,archived_time FROM hf_project'))).one(), ('0', 1, None))

    async def test_listing_scope_before_count_and_literal_search(self):
        from module_higgsfield.entity.vo.project_governance_vo import ProjectGovernanceQuery
        async def listing(**values):
            async with self.sessions() as db:
                return await ProjectGovernanceService.listing(db, self.actor, ProjectGovernanceQuery(**values))
        self.assertEqual((await listing()).total, 0)
        await self.scope('3')
        self.assertEqual((await listing()).total, 0)
        await self.scope('4')
        result = await listing(pageSize=1)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]['id'], str(self.project_id))
        self.assertFalse(result.has_next)
        self.assertEqual((await listing(q='%')).total, 0)
        await self.create(name='项目_100%')
        result = await listing(q='_100%', pageSize=1)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]['name'], '项目_100%')
        self.assertEqual((await listing(status='archived')).total, 0)
        self.assertEqual((await listing(pageNum=2, pageSize=1)).total, 2)
        async with self.sessions() as db:
            await db.execute(text("UPDATE sys_user SET dept_id=110 WHERE user_id=1"))
            await db.commit()
        self.assertEqual((await listing()).total, 0)
        await self.scope('1')
        self.assertEqual((await listing()).total, 2)

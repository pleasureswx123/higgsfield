"""管理成本中心真实迁移、授权范围及可用状态过滤。"""
import importlib.util
import os
import unittest
from pathlib import Path
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import PermissionException
from tests import test_higgsfield_admin_scope as scopes
from module_higgsfield.entity.vo.cost_center_vo import CostCenterQuery
from module_higgsfield.service.cost_center_service import CostCenterService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CostCenterTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = scopes.AdminScopeTests.cleanup_schema
    create = scopes.AdminScopeTests.create
    scope = scopes.AdminScopeTests.scope

    async def asyncSetUp(self):
        await scopes.AdminScopeTests.asyncSetUp(self)
        self.actor.permissions = ['credential:test', 'billing:read']
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE sys_menu SET perms='credential:test' WHERE menu_id=9001"))
            spec = importlib.util.spec_from_file_location('cost_center_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_56_cost_centers.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade()
            await conn.run_sync(migrate)

    async def listing(self, **values):
        async with self.sessions() as db:
            return await CostCenterService.listing(db, self.actor, CostCenterQuery(**values))

    async def test_global_permission_filter_and_live_revocation(self):
        with self.assertRaises(PermissionException):
            await self.listing()
        await self.scope('1')
        page = await self.listing()
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]['code'], 'admin_test')
        self.assertTrue(page.rows[0]['active'])
        async with self.sessions() as db:
            await db.execute(text("UPDATE sys_menu SET perms='billing:read' WHERE menu_id=9001"))
            await db.execute(text("INSERT INTO hf_cost_center(cost_center_id,code,cost_center_name,active,create_time,update_time) VALUES (9007199254740993,'extra','额外归属','Y',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),(9007199254740994,'disabled','停用归属','N',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            await db.commit()
        # 测试权限已失效时仍可由费用读取权限独立授权，停用记录不进入计数。
        page = await self.listing(pageSize=1, pageNum=2)
        self.assertEqual(page.total, 2)
        self.assertEqual(page.rows[0]['id'], '9007199254740993')
        self.assertFalse(page.has_next)
        async with self.sessions() as db:
            await db.execute(text('DELETE FROM sys_role_menu WHERE menu_id=9001'))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.listing()

    async def test_migration_comments_no_foreign_keys_and_unique_code(self):
        from sqlalchemy.exc import IntegrityError
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_cost_center'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_cost_center'::regclass AND contype='f'")), 0)
            with self.assertRaises(IntegrityError):
                await db.execute(text("INSERT INTO hf_cost_center(code,cost_center_name,create_time,update_time) VALUES ('admin_test','重复',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))

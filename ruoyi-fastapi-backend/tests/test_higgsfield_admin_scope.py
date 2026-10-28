"""管理范围按授予当前功能的角色隔离，不借用其他角色的全部范围。"""

import os
import unittest
from types import SimpleNamespace
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.routing_service import RoutingService
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class AdminScopeTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        result, _ = await self.create()
        self.project_id = int(result['data']['id'])
        self.actor = SimpleNamespace(user=SimpleNamespace(user_id=2, admin=False), permissions=['provider:route'])
        async with self.engine.begin() as db:
            for sql in (
                'ALTER TABLE sys_user ADD COLUMN dept_id bigint',
                'CREATE TABLE sys_role (role_id bigint PRIMARY KEY,data_scope char(1),status char(1),del_flag char(1))',
                'CREATE TABLE sys_user_role (user_id bigint,role_id bigint)',
                'CREATE TABLE sys_role_menu (role_id bigint,menu_id bigint)',
                'CREATE TABLE sys_role_dept (role_id bigint,dept_id bigint)',
                'CREATE TABLE sys_dept (dept_id bigint PRIMARY KEY,ancestors text,status char(1),del_flag char(1))',
                "INSERT INTO sys_dept VALUES (10,'0','0','0'),(11,'0,10','0','0'),(110,'0,1','0','0')",
                'UPDATE sys_user SET dept_id=CASE WHEN user_id=1 THEN 11 ELSE 10 END',
                "INSERT INTO sys_role VALUES (1,'1','0','0'),(2,'5','0','0')",
                'INSERT INTO sys_user_role VALUES (2,1),(2,2)',
                "INSERT INTO sys_menu (menu_id,status,perms) VALUES (9001,'0','provider:route'),(9002,'0','unrelated:read')",
                'INSERT INTO sys_role_menu VALUES (1,9002),(2,9001)',
            ):
                await db.execute(text(sql))

    async def scope(self, value):
        async with self.sessions() as db:
            await db.execute(text('UPDATE sys_role SET data_scope=:scope WHERE role_id=2'), {'scope': value})
            await db.commit()

    async def test_role_isolation_live_revocation_and_global_scope(self):
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
            with self.assertRaises(PermissionException):
                await AdminScopeService.global_access(db, self.actor, 'provider:route')
        await self.scope('1')
        async with self.sessions() as db:
            self.assertEqual(
                (await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route'))['project_id'],
                self.project_id,
            )
            await AdminScopeService.global_access(db, self.actor, 'provider:route')
            self.assertEqual(
                await RoutingService.get(db, self.actor, self.project_id),
                {'projectId': str(self.project_id), 'revision': '1', 'routes': []},
            )
            await db.execute(text('DELETE FROM sys_role_menu WHERE role_id=2'))
            await db.commit()
            with self.assertRaises(PermissionException):
                await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')

    async def test_department_tree_custom_and_self(self):
        await self.scope('3')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
        await self.scope('4')
        async with self.sessions() as db:
            await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
            # 10 不得误匹配 110 或祖先1，PostgreSQL数组按完整节点匹配。
            await db.execute(text('UPDATE sys_user SET dept_id=110 WHERE user_id=1'))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
        await self.scope('2')
        async with self.sessions() as db:
            await db.execute(text('INSERT INTO sys_role_dept VALUES (2,110)'))
            await db.commit()
            await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
        await self.scope('5')
        async with self.sessions() as db:
            await db.execute(
                text('UPDATE hf_project SET create_user_id=2 WHERE project_id=:id'), {'id': self.project_id}
            )
            await db.commit()
            await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route')
            await db.execute(text("UPDATE hf_project SET status='1' WHERE project_id=:id"), {'id': self.project_id})
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await AdminScopeService.project(db, self.actor, self.project_id, 'provider:route', write=True)
            self.assertEqual(
                await db.scalar(
                    text('SELECT revision FROM hf_project_routing_set WHERE project_id=:id'), {'id': self.project_id}
                ),
                1,
            )

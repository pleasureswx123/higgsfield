"""真实隔离数据库证明审计范围先于分页，历史事实保留且撤权生效。"""
import importlib.util
import os
import unittest
from pathlib import Path
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import PermissionException
from tests import test_higgsfield_admin_scope as scope_tests
from module_higgsfield.entity.vo.audit_query_vo import AuditQuery
from module_higgsfield.service.audit_read_service import AuditReadService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class AuditReadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = scope_tests.AdminScopeTests.cleanup_schema
    create = scope_tests.AdminScopeTests.create
    scope = scope_tests.AdminScopeTests.scope

    async def asyncSetUp(self):
        await scope_tests.AdminScopeTests.asyncSetUp(self)
        self.actor.permissions = ['audit:read']
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE sys_menu SET perms='audit:read' WHERE menu_id=9001"))
            for name in ['20261027_16_audit.py', '20261028_50_audit_read.py', '20261028_50_audit_read.py']:
                spec = importlib.util.spec_from_file_location('audit_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
            await conn.execute(text("""INSERT INTO hf_audit_log
                (actor_id,actor_kind,project_id,object_type,object_id,action,request_id,before_after,reason,create_time,update_time)
                VALUES (2,'user',:project,'project','9007199254740993','pause','req1',
                '{"before":{"status":"active"},"after":{"status":"paused"}}','维护','2026-10-01T00:00:00Z',CURRENT_TIMESTAMP),
                (NULL,'system',NULL,'configuration','global','update','req2','{}',NULL,'2026-10-02T00:00:00Z',CURRENT_TIMESTAMP)"""),
                {'project': self.project_id})

    async def listing(self, **values):
        async with self.sessions() as db:
            return await AuditReadService.listing(db, self.actor, AuditQuery(**values))

    async def test_scope_filter_history_and_revocation(self):
        # 自己执行过操作不等于拥有项目管理范围，无关全局角色不扩大范围。
        self.assertEqual((await self.listing()).total, 0)
        await self.scope('3')
        self.assertEqual((await self.listing()).total, 0)
        await self.scope('4')
        page = await self.listing(pageSize=1)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]['objectId'], '9007199254740993')
        self.assertEqual(page.rows[0]['actorId'], '2')
        self.assertEqual(page.rows[0]['diff']['after']['status'], 'paused')
        self.assertNotIn('requestId', page.rows[0])
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project SET del_flag='2'"))
            await db.commit()
        self.assertEqual((await self.listing()).total, 1)
        await self.scope('1')
        page = await self.listing(pageSize=1)
        self.assertEqual(page.total, 2)
        self.assertTrue(page.has_next)
        self.assertIsNone(page.rows[0]['actorId'])
        self.assertEqual((await self.listing(pageNum=2, pageSize=1)).rows[0]['action'], 'pause')
        async with self.sessions() as db:
            await db.execute(text('DELETE FROM sys_role_menu WHERE menu_id=9001'))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.listing()

    async def test_exact_filters_and_half_open_time(self):
        await self.scope('1')
        self.assertEqual((await self.listing(objectType='project', objectId='9007199254740993', actorId='2')).total, 1)
        self.assertEqual((await self.listing(objectId='%')).total, 0)
        self.assertEqual((await self.listing(**{'from': '2026-10-01T08:00:00+08:00', 'to': '2026-10-02T00:00:00Z'})).total, 1)
        self.assertEqual((await self.listing(**{'from': '2026-10-02T00:00:00Z'})).total, 1)


class AuditQueryTests(unittest.TestCase):
    def test_rejects_ambiguous_time_and_invalid_identity(self):
        from pydantic import ValidationError
        for values in ({'from': '2026-10-01T00:00:00'},
                       {'from': '2026-10-02T00:00:00Z', 'to': '2026-10-01T00:00:00Z'},
                       {'actorId': 2}, {'actorId': '0'}, {'pageSize': 101}):
            with self.assertRaises(ValidationError, msg=str(values)):
                AuditQuery(**values)

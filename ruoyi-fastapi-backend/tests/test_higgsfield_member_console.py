"""后台成员入口迁移不扩权，并继续使用项目授权约束。"""

import importlib.util
import os
import unittest
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class MemberConsoleDatabaseTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = projects.ProjectDatabaseTests.asyncSetUp
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def test_menu_is_idempotent_and_does_not_grant_roles(self):
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_menu ADD COLUMN component text'))
            before = (await conn.execute(text('SELECT count(*) FROM hf_project_role_permission'))).scalar()
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_05_member_console.py'
            spec = importlib.util.spec_from_file_location('member_console_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()
                    module.upgrade()

            await conn.run_sync(migrate)
            self.assertEqual(
                (
                    await conn.execute(
                        text("SELECT count(*) FROM sys_menu WHERE component='studio/projectMembers/index'")
                    )
                ).scalar(),
                1,
            )
            self.assertEqual(
                (await conn.execute(text('SELECT count(*) FROM hf_project_role_permission'))).scalar(), before
            )

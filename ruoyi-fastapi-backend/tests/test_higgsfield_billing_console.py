"""费用页面真实迁移幂等且不自动赋予项目或系统角色权限。"""

import importlib.util
import os
import unittest
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BillingConsoleTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = projects.ProjectDatabaseTests.asyncSetUp
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def test_menu_is_idempotent_and_does_not_grant_permissions(self):
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_menu ADD COLUMN component text, ADD COLUMN icon text'))
            before = (await conn.execute(text('SELECT count(*) FROM hf_project_role_permission'))).scalar()
            for filename in ('20261027_05_member_console.py', '20261028_42_billing_console.py', '20261028_42_billing_console.py', '20261028_43_budget_console.py', '20261028_43_budget_console.py', '20261028_44_model_console.py', '20261028_44_model_console.py', '20261028_45_routing_console.py', '20261028_45_routing_console.py', '20261028_46_price_console.py', '20261028_46_price_console.py', '20261028_49_governance_console.py', '20261028_49_governance_console.py', '20261028_51_audit_console.py', '20261028_51_audit_console.py', '20261028_53_call_console.py', '20261028_53_call_console.py', '20261028_55_incident_console.py', '20261028_55_incident_console.py', '20261028_64_reconciliation_console.py', '20261028_64_reconciliation_console.py'):
                spec = importlib.util.spec_from_file_location(
                    'billing_console_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / filename
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()

                await conn.run_sync(migrate)
            row = (await conn.execute(text(
                "SELECT m.perms,m.visible FROM sys_menu m JOIN sys_menu p ON p.menu_id=m.parent_id "
                "WHERE m.component='studio/billing/index' AND p.path='studio'"
            ))).one()
            self.assertEqual(tuple(row), ('billing:read', '0'))
            budget = (await conn.execute(text(
                "SELECT m.perms,m.visible FROM sys_menu m JOIN sys_menu p ON p.menu_id=m.parent_id "
                "WHERE m.component='studio/budgets/index' AND p.path='studio'"
            ))).one()
            self.assertEqual(tuple(budget), ('billing:budget:read', '0'))
            model = (await conn.execute(text(
                "SELECT m.perms,m.visible FROM sys_menu m JOIN sys_menu p ON p.menu_id=m.parent_id "
                "WHERE m.component='studio/models/index' AND p.path='studio'"
            ))).one()
            self.assertEqual(tuple(model), ('model:read', '0'))
            routing = (await conn.execute(text(
                "SELECT perms,visible FROM sys_menu WHERE component='studio/routing/index'"
            ))).one()
            self.assertEqual(tuple(routing), ('provider:route', '0'))
            prices = (await conn.execute(text(
                "SELECT perms,visible FROM sys_menu WHERE component='studio/prices/index'"
            ))).one()
            self.assertEqual(tuple(prices), ('billing:price:read', '0'))
            governance = (await conn.execute(text("SELECT perms,visible FROM sys_menu WHERE component='studio/governance/index'"))).one()
            self.assertEqual(tuple(governance), ('project:govern', '0'))
            audit = (await conn.execute(text("SELECT perms,visible FROM sys_menu WHERE component='studio/audit/index'"))).one()
            self.assertEqual(tuple(audit), ('audit:read', '0'))
            calls = (await conn.execute(text("SELECT perms,visible FROM sys_menu WHERE component='studio/calls/index'"))).one()
            self.assertEqual(tuple(calls), ('operations:read', '0'))
            incidents = (await conn.execute(text("SELECT perms,visible FROM sys_menu WHERE component='studio/incidents/index'"))).one()
            self.assertEqual(tuple(incidents), ('operations:read', '0'))
            reconciliation = (await conn.execute(text("SELECT perms,visible FROM sys_menu WHERE component='studio/reconciliations/index'"))).one()
            self.assertEqual(tuple(reconciliation), ('billing:read', '0'))
            self.assertEqual((await conn.execute(text('SELECT count(*) FROM hf_project_role_permission'))).scalar(), before)

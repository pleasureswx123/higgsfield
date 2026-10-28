"""预算定义接口事务与分页前数据范围验证。"""

import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from pydantic import ValidationError
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.service.budget_period_service import BudgetPeriodService
from module_higgsfield.entity.vo.budget_vo import BudgetCreate, BudgetUpdate, BudgetQuery
from module_higgsfield.service.budget_service import BudgetService
from tests import test_higgsfield_admin_scope as scope


class BudgetInputTests(unittest.TestCase):
    def test_explicit_subject_and_timezone(self):
        base = dict(
            subject={'userId': '1'},
            purpose='platform',
            currency='CNY',
            cycleKind='monthly',
            businessTimezone='Asia/Shanghai',
        )
        for changes in (
            {'subject': {}},
            {'subject': {'userId': '1', 'projectId': '1'}},
            {'businessTimezone': 'invalid/timezone'},
        ):
            with self.assertRaises(ValidationError):
                BudgetCreate(**(base | changes))
        with self.assertRaises(ValidationError):
            BudgetQuery(subjectId='1')
        with self.assertRaises(ValidationError):
            BudgetUpdate(revision='1', active=1)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BudgetTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = scope.AdminScopeTests.cleanup_schema
    create = scope.AdminScopeTests.create
    scope = scope.AdminScopeTests.scope

    async def asyncSetUp(self):
        await scope.AdminScopeTests.asyncSetUp(self)
        self.owner.user.admin = True
        self.actor.user.user_name = 'other'
        self.actor.permissions = ['billing:budget', 'billing:budget:read']
        async with self.engine.begin() as conn:
            for filename in (
                '20261027_16_model_lifecycle.py',
                '20261027_27_budgets.py',
                '20261027_26_exchange_rates.py',
                '20261027_28_budget_permissions.py',
            ):
                path = Path(__file__).resolve().parents[1] / 'alembic/versions' / filename
                if not path.exists() and filename.startswith('20261027_16'):
                    path = next(path.parent.glob('20261027_16*.py'))
                spec = importlib.util.spec_from_file_location('budget_api_migration', path)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)

                def execute(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        migration.upgrade()

                await conn.run_sync(execute)
            await conn.execute(
                text(
                    "INSERT INTO sys_role_menu(role_id,menu_id) SELECT 2,menu_id FROM sys_menu WHERE perms IN ('billing:budget','billing:budget:read')"
                )
            )

    def payload(self, subject=None, **changes):
        return BudgetCreate(
            **(
                dict(
                    subject=subject or {'userId': '1'},
                    purpose='platform',
                    currency='CNY',
                    cycleKind='monthly',
                    businessTimezone='Asia/Shanghai',
                )
                | changes
            )
        )

    async def save_budget(self, payload, user=None, key=None, identity=None):
        async with self.sessions() as db:
            return await BudgetService.save(db, user or self.owner, payload, key or str(uuid4()), identity)

    async def test_creation_replay_toggle_and_stale_revision(self):
        key = str(uuid4())
        result, _ = await self.save_budget(self.payload(), key=key)
        repeated, replay = await self.save_budget(self.payload(), key=key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        identity = result['data']['id']
        with self.assertRaises(ServiceWarning):
            await self.save_budget(self.payload())
        changed, _ = await self.save_budget(BudgetUpdate(revision='1', active=False), identity=identity)
        self.assertFalse(changed['data']['active'])
        with self.assertRaises(ServiceWarning):
            await self.save_budget(BudgetUpdate(revision='1', active=True), identity=identity)

    async def test_scope_filtering_before_count_and_write(self):
        own, _ = await self.save_budget(self.payload({'userId': '2'}))
        other, _ = await self.save_budget(self.payload({'userId': '1'}))
        await self.save_budget(self.payload({'projectId': str(self.project_id)}))
        async with self.sessions() as db:
            page = await BudgetService.listing(db, self.actor, BudgetQuery(pageSize=1))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['id'], own['data']['id'])
        with self.assertRaises(ServiceWarning):
            await self.save_budget(
                BudgetUpdate(revision='1', active=False), user=self.actor, identity=other['data']['id']
            )
        await self.scope('4')
        async with self.sessions() as db:
            page = await BudgetService.listing(db, self.actor, BudgetQuery(pageSize=1))
            self.assertEqual(page.total, 3)
            self.assertTrue(page.has_next)

    async def test_procurement_cannot_leak_through_scoped_budget_access(self):
        platform, _ = await self.save_budget(self.payload({'userId': '2'}))
        purchase, _ = await self.save_budget(self.payload({'userId': '2'}, purpose='procurement'))
        async with self.sessions() as db:
            page = await BudgetService.listing(db, self.actor, BudgetQuery(pageSize=1))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['id'], platform['data']['id'])
            hidden = await BudgetService.listing(db, self.actor, BudgetQuery(purpose='procurement'))
            self.assertEqual(hidden.total, 0)
            with self.assertRaises(ServiceWarning):
                await BudgetPeriodService.authorize(db, self.actor, purchase['data']['id'], 'billing:budget:read')
            with self.assertRaises(ServiceWarning):
                await BudgetPeriodService.authorize(db, self.actor, purchase['data']['id'], 'billing:budget', write=True)
        with self.assertRaises(PermissionException):
            await self.save_budget(self.payload({'userId': '2'}, purpose='procurement', currency='USD'), user=self.actor)
        with self.assertRaises(PermissionException):
            await self.save_budget(BudgetUpdate(revision='1', active=False), user=self.actor, identity=purchase['data']['id'])
        await self.scope('1')
        async with self.sessions() as db:
            page = await BudgetService.listing(db, self.actor, BudgetQuery(purpose='procurement'))
            self.assertEqual(page.total, 1)

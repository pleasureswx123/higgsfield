"""供应商账号四维唯一作用域和后台权限测试。"""

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.provider_vo import ProviderAccountCreate, ProviderAccountQuery
from module_higgsfield.service.provider_service import ProviderService
from tests import test_higgsfield_models as models


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderAccountTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = models.ModelTests.cleanup_schema

    async def asyncSetUp(self):
        await models.ModelTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'provider_account_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_15_provider_accounts.py',
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)

    async def make(self, key=None, region='eva', upstream='upstream-project'):
        async with self.sessions() as db:
            return await ProviderService.create_account(
                db,
                self.owner,
                ProviderAccountCreate(
                    connectionId=self.connection_id,
                    accountCode='company-account',
                    region=region,
                    upstreamProject=upstream,
                ),
                key or str(uuid4()),
            )

    async def test_scope_replay_and_pagination(self):
        key = str(uuid4())
        first, _ = await self.make(key)
        replay, repeated = await self.make(key)
        self.assertTrue(repeated)
        self.assertEqual(first, replay)
        with self.assertRaises(ServiceWarning):
            await self.make()
        other_region, _ = await self.make(region='nova')
        other_project, _ = await self.make(upstream='second-project')
        self.assertNotEqual(first['data']['id'], other_region['data']['id'])
        self.assertNotEqual(first['data']['id'], other_project['data']['id'])
        async with self.sessions() as db:
            page = await ProviderService.accounts(db, self.owner, ProviderAccountQuery(region='eva', pageSize=1))
            self.assertEqual(page.total, 2)
            self.assertEqual(len(page.rows), 1)
            self.assertTrue(page.has_next)
            exact = await ProviderService.accounts(db, self.owner, ProviderAccountQuery(accountId=first['data']['id']))
            self.assertEqual(exact.total, 1)
            self.assertEqual(exact.rows[0]['id'], first['data']['id'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_account')), 3)

    async def test_permissions_and_disabled_connection(self):
        limited = SimpleNamespace(user=self.owner.user, permissions=['model:read'])
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ProviderService.accounts(db, limited, ProviderAccountQuery())
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_connection SET status='2'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.make()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_account')), 0)
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid='hf_provider_account'::regclass AND contype='f'"
                    )
                ),
                0,
            )
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_attribute WHERE attrelid='hf_provider_account'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                    )
                ),
                0,
            )

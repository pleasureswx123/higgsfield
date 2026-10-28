"""价格簿真实事务、幂等重试和采购范围测试。"""

import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.price_vo import PriceBookCreate, PriceBookQuery
from module_higgsfield.service.price_service import PriceService
from tests import test_higgsfield_routing as routing


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceBookTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = routing.RoutingTests.cleanup_schema

    async def asyncSetUp(self):
        await routing.RoutingTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            for filename in ('20261027_22_prices.py', '20261027_23_price_permissions.py'):
                spec = importlib.util.spec_from_file_location(
                    'price_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / filename
                )
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)

                def execute(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        migration.upgrade()

                await conn.run_sync(execute)
            self.variant_id = str(
                await conn.scalar(
                    text(
                        "INSERT INTO hf_model_variant(model_version_id,variant_key,dimensions,create_time,update_time) SELECT model_version_id,'test','{}'::jsonb,NOW(),NOW() FROM hf_model_profile_version WHERE model_id=:id RETURNING variant_id"
                    ),
                    {'id': int(self.model_id)},
                )
            )

    def payload(self, **changes):
        values = dict(modelVariantId=self.variant_id, purpose='platform', currency='CNY', name='测试价格')
        values.update(changes)
        return PriceBookCreate(**values)

    async def create(self, payload, key=None):
        async with self.sessions() as db:
            return await PriceService.create(db, self.owner, payload, key or str(uuid4()))

    async def test_replay_unique_and_filtered_listing(self):
        key = str(uuid4())
        result, replay = await self.create(self.payload(), key)
        self.assertFalse(replay)
        repeated, replay = await self.create(self.payload(), key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        with self.assertRaises(ServiceWarning):
            await self.create(self.payload())
        await self.create(self.payload(currency='USD'))
        async with self.sessions() as db:
            page = await PriceService.listing(db, self.owner, PriceBookQuery(currency='CNY'))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['id'], result['data']['id'])
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await PriceService.listing(db, self.owner, PriceBookQuery())

    async def test_procurement_region_validation(self):
        result, _ = await self.create(self.payload(purpose='procurement', accountId=self.account_id))
        self.assertEqual(result['data']['accountId'], self.account_id)
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_provider_account SET region='other' WHERE account_id=:id"), {'id': int(self.account_id)}
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.create(self.payload(purpose='procurement', accountId=self.account_id, currency='USD'))

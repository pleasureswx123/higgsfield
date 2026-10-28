"""汇率双向精度、时段边界及币对发布并发。"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.exchange_rate_vo import ExchangeRateCreate, ExchangeRatePublish, ExchangeRateQuery
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from tests import test_higgsfield_price_versions as versions
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.entity.vo.price_version_vo import PriceSimulation


class ConversionTests(unittest.TestCase):
    def test_documented_bidirectional_values_and_boundaries(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2027, 1, 1, tzinfo=timezone.utc)
        row = SimpleNamespace(
            exchange_rate_id=1,
            base_currency='USD',
            quote_currency='CNY',
            rate=Decimal('6.69'),
            status='1',
            valid_from=start,
            valid_until=end,
        )
        forward = ExchangeRateService.convert(row, '0.0627', 'USD', 'CNY', at=start, scale=10)
        self.assertEqual(forward['amount'], '0.4194630000')
        reverse = ExchangeRateService.convert(row, '42', 'CNY', 'USD', at=start, scale=10)
        self.assertEqual(reverse['amount'], '6.2780269058')
        self.assertEqual(reverse['direction'], 'divide')
        for source, target, at in [('USD', 'CNY', end), ('EUR', 'CNY', start), ('USD', 'USD', start)]:
            with self.assertRaises(ValueError):
                ExchangeRateService.convert(row, '1', source, target, at=at, scale=10)
        row.status = '0'
        with self.assertRaises(ValueError):
            ExchangeRateService.convert(row, '1', 'USD', 'CNY', at=start, scale=10)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ExchangeRateTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = versions.PriceVersionTests.cleanup_schema

    async def asyncSetUp(self):
        await versions.PriceVersionTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'rate_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_26_exchange_rates.py'
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:

            def execute(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(execute)

    async def create(self, key=None, **changes):
        payload = ExchangeRateCreate(
            **(
                dict(
                    baseCurrency='USD',
                    quoteCurrency='CNY',
                    rate='6.69',
                    sourceId=self.source_id,
                    validFrom='2027-01-01T00:00:00Z',
                    validUntil='2027-02-01T00:00:00Z',
                )
                | changes
            )
        )
        async with self.sessions() as db:
            return await ExchangeRateService.save(db, self.owner, payload, key or str(uuid4()))

    async def publish(self, identity, key=None):
        async with self.sessions() as db:
            return await ExchangeRateService.save(
                db, self.owner, ExchangeRatePublish(revision='1', reason='核对报价依据'), key or str(uuid4()), identity
            )

    async def test_replay_publish_and_filtered_listing(self):
        key = str(uuid4())
        result, _ = await self.create(key)
        repeated, replay = await self.create(key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        identity = result['data']['id']
        key = str(uuid4())
        result, _ = await self.publish(identity, key)
        repeated, replay = await self.publish(identity, key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        self.assertEqual(result['data']['status'], 'published')
        async with self.sessions() as db:
            page = await ExchangeRateService.listing(db, self.owner, ExchangeRateQuery(baseCurrency='USD'))
            self.assertEqual(page.total, 1)
            self.assertEqual(Decimal(page.rows[0]['rate']), Decimal('6.69'))

    async def test_reverse_pair_concurrency_and_adjacent_interval(self):
        first, _ = await self.create()
        second, _ = await self.create(baseCurrency='CNY', quoteCurrency='USD', rate='0.15')
        outcomes = await asyncio.gather(
            self.publish(first['data']['id']), self.publish(second['data']['id']), return_exceptions=True
        )
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in outcomes), 1)
        self.assertEqual(sum(isinstance(value, tuple) for value in outcomes), 1)
        adjacent, _ = await self.create(validFrom='2027-02-01T00:00:00Z', validUntil=None)
        await self.publish(adjacent['data']['id'])

    async def test_price_simulation_keeps_original_currency(self):
        rate, _ = await self.create(validFrom='2020-01-01T00:00:00Z', validUntil=None)
        await self.publish(rate['data']['id'])
        async with self.sessions() as db:
            price, _ = await PriceVersionService.save(
                db,
                self.owner,
                versions.PriceVersionTests.payload(self, items=[versions.rule(unitPrice='42')]),
                str(uuid4()),
            )
            result = await PriceVersionService.simulate(
                db,
                self.owner,
                price['data']['id'],
                PriceSimulation(
                    dimensions={}, usage={'videoTokens': '1000000'}, exchangeRateVersionId=rate['data']['id']
                ),
            )
            self.assertEqual((result['currency'], result['total']), ('CNY', '42.0000000000'))
            self.assertEqual(result['conversion']['amount'], '6.2780269058')
            self.assertEqual(result['conversion']['targetCurrency'], 'USD')
            with self.assertRaises(ServiceWarning):
                await PriceVersionService.simulate(
                    db,
                    self.owner,
                    price['data']['id'],
                    PriceSimulation(
                        dimensions={}, usage={'videoTokens': '1'}, exchangeRateVersionId='9223372036854775807'
                    ),
                )

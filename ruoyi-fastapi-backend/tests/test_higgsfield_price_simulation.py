"""保存后的价格版本试算与只读边界。"""

import os
import unittest
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.price_version_vo import PriceSimulation, SimulationUsage
from module_higgsfield.service.price_version_service import PriceVersionService
from tests import test_higgsfield_price_versions as versions
from tests import test_higgsfield_exchange_rates as rates


class SimulationInputTests(unittest.TestCase):
    def test_strict_quantities(self):
        for values in (
            {'videoTokens': 1},
            {'videoTokens': '1.5'},
            {'videoTokens': None},
            {'videoTokens': '9223372036854775808'},
            {'outputSeconds': 0.5},
            {'imageCount': True},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SimulationUsage(**values)
        self.assertEqual(SimulationUsage(videoTokens='0').video_tokens, '0')
        with self.assertRaises(ValidationError):
            PriceSimulation(dimensions={'fps': float('nan')}, usage={})


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceSimulationTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = versions.PriceVersionTests.cleanup_schema

    async def asyncSetUp(self):
        await rates.ExchangeRateTests.asyncSetUp(self)
        async with self.sessions() as db:
            result, _ = await PriceVersionService.save(
                db, self.owner, versions.PriceVersionTests.payload(self), str(uuid4())
            )
            self.version_id = result['data']['id']

    async def test_documented_amount_and_no_writes(self):
        async with self.sessions() as db:
            before = await db.scalar(text('SELECT count(*) FROM hf_audit_log'))
            request = PriceSimulation(dimensions={}, usage={'videoTokens': '108000'})
            first = await PriceVersionService.simulate(db, self.owner, self.version_id, request)
            second = await PriceVersionService.simulate(db, self.owner, self.version_id, request)
            self.assertEqual(first, second)
            self.assertEqual(first['total'], '7.5600000000')
            self.assertEqual(first['currency'], 'CNY')
            self.assertEqual(first['matchedVariantId'], self.variant_id)
            self.assertTrue(first['warnings'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), before)
            version = await PriceVersionService.get(db, self.owner, self.version_id)
            self.assertEqual(version['revision'], '1')

    async def test_missing_usage_mismatched_dimensions_rate_and_permission(self):
        async with self.sessions() as db:
            requests = [
                PriceSimulation(dimensions={}, usage={}),
                PriceSimulation(dimensions={'resolution': '720p'}, usage={'videoTokens': '1'}),
                PriceSimulation(dimensions={}, usage={'videoTokens': '1'}, exchangeRateVersionId='1'),
            ]
            for request in requests:
                with self.assertRaises(ServiceWarning):
                    await PriceVersionService.simulate(db, self.owner, self.version_id, request)
            await db.execute(
                text('UPDATE hf_model_variant SET dimensions=CAST(:dimensions AS jsonb) WHERE variant_id=:id'),
                {'id': int(self.variant_id), 'dimensions': '{"enabled":true}'},
            )
            with self.assertRaises(ServiceWarning):
                await PriceVersionService.simulate(
                    db,
                    self.owner,
                    self.version_id,
                    PriceSimulation(dimensions={'enabled': 1}, usage={'videoTokens': '1'}),
                )
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await PriceVersionService.simulate(
                    db,
                    self.owner,
                    self.version_id,
                    PriceSimulation(dimensions={'enabled': True}, usage={'videoTokens': '1'}),
                )

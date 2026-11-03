"""双账价格原子切换、重放和历史正文保留的隔离数据库验证。"""
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.price_vo import PriceBookCreate
from module_higgsfield.entity.vo.price_publish_vo import PriceBatchPublish
from module_higgsfield.service.price_service import PriceService
from module_higgsfield.service.model_price_batch_service import ModelPriceBatchService
from module_higgsfield.service.price_version_service import PriceVersionService
from tests.test_higgsfield_price_publish import PricePublishTests
from tests.test_higgsfield_price_versions import rule


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要启用隔离数据库测试')
class ModelPriceBatchTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = PricePublishTests.cleanup_schema
    payload = PricePublishTests.payload
    save = PricePublishTests.save
    draft = PricePublishTests.draft

    async def asyncSetUp(self):
        await PricePublishTests.asyncSetUp(self)
        self.books = []
        async with self.sessions() as db:
            for purpose in ('platform', 'procurement'):
                result, _ = await PriceService.create(db, self.owner, PriceBookCreate(
                    modelVariantId=self.variant_id, purpose=purpose, currency='USD', name='同步价格测试',
                    accountId=self.account_id if purpose == 'procurement' else None), str(uuid4()))
                self.books.append(result['data']['id'])

    async def pair(self, price='42', old=None):
        items = []
        for index, book in enumerate(self.books):
            identity = await self.draft(priceBookId=book, items=[rule(unitPrice=price, unitQuantity='6690000')])
            items.append(dict(versionId=identity, revision='1', expectedActivationId=old[index] if old else None))
        return PriceBatchPublish(items=items, reason='测试同步改价')

    async def publish(self, payload, key=None):
        async with self.sessions() as db:
            return await ModelPriceBatchService.publish(db, self.owner, payload, key or str(uuid4()))

    async def test_atomic_replace_replay_preserves_old_price(self):
        first = await self.pair()
        original, _ = await self.publish(first)
        old = [row['activation']['id'] for row in original['data']['prices']]
        async with self.sessions() as db:
            frozen = [await PriceVersionService.get(db, self.owner, item.version_id) for item in first.items]
        replacement = await self.pair('43', old)
        key = str(uuid4())
        result, _ = await self.publish(replacement, key)
        repeated, replay = await self.publish(replacement, key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        starts = [row['activation']['effectiveFrom'] for row in result['data']['prices']]
        self.assertEqual(starts[0], starts[1])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_activation WHERE effective_until IS NULL')), 2)
            for item, snapshot in zip(first.items, frozen):
                self.assertEqual(await PriceVersionService.get(db, self.owner, item.version_id), snapshot)

    async def test_second_price_failure_rolls_back_first(self):
        payload = await self.pair()
        payload.items[1].revision = '999'
        with self.assertRaises(ServiceWarning):
            await self.publish(payload)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_activation')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_publish_event')), 0)
            for item in payload.items:
                self.assertEqual((await PriceVersionService.get(db, self.owner, item.version_id))['status'], 'draft')

    async def test_stale_activation_rejected(self):
        await self.publish(await self.pair())
        with self.assertRaises(ServiceWarning):
            await self.publish(await self.pair('43'))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_activation')), 2)

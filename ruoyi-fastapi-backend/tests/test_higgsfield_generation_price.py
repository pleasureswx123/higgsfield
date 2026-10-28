"""受理价格固定的账号边界、半开区间和历史快照测试。"""

import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.service.generation_price_service import GenerationPriceService
from tests import test_higgsfield_price_publish as publish


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationPriceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = publish.PricePublishTests.cleanup_schema
    payload = publish.PricePublishTests.payload
    save = publish.PricePublishTests.save
    draft = publish.PricePublishTests.draft
    publish = publish.PricePublishTests.publish

    async def asyncSetUp(self) -> None:
        await publish.PricePublishTests.asyncSetUp(self)
        self.price_id = await self.draft()
        await self.publish(self.price_id)
        async with self.sessions() as db:
            book = await db.scalar(
                text(
                    "INSERT INTO hf_price_book(model_variant_id,purpose,account_id,currency,price_book_name,create_time,update_time) VALUES(:v,'procurement',:a,'USD','采购测试',NOW(),NOW()) RETURNING price_book_id"
                ),
                {'v': int(self.variant_id), 'a': int(self.account_id)},
            )
            version = await db.scalar(
                text(
                    "INSERT INTO hf_price_version(price_book_id,version_no,status,rounding_mode,calculation_scale,create_user_id,create_time,update_time) VALUES(:b,1,'1','half_up',6,1,NOW(),NOW()) RETURNING price_version_id"
                ),
                {'b': book},
            )
            await db.execute(
                text(
                    'INSERT INTO hf_price_rule_item(price_version_id,item_code,unit,unit_quantity,unit_price,quantity_from,formula_template,create_time,update_time) SELECT :v,item_code,unit,unit_quantity,unit_price,quantity_from,formula_template,NOW(),NOW() FROM hf_price_rule_item WHERE price_version_id=:p'
                ),
                {'v': version, 'p': int(self.price_id)},
            )
            await db.execute(
                text(
                    'INSERT INTO hf_price_version_source(price_version_id,source_id,create_time,update_time) VALUES(:v,:s,NOW(),NOW())'
                ),
                {'v': version, 's': int(self.source_id)},
            )
            await db.execute(
                text(
                    "INSERT INTO hf_price_activation(price_book_id,price_version_id,effective_from,create_time,update_time) VALUES(:b,:v,'2027-01-01T00:00:00Z',NOW(),NOW())"
                ),
                {'b': book, 'v': version},
            )
            await db.commit()

    async def freeze(self, *, account_id: int | None = None, at: str = '2027-01-01T00:00:00+00:00') -> dict:
        async with self.sessions() as db:
            return await GenerationPriceService.freeze(
                db,
                variant_id=int(self.variant_id),
                account_id=account_id or int(self.account_id),
                currencies={'platform': 'CNY', 'procurement': 'USD'},
                at=datetime.fromisoformat(at),
            )

    async def test_pair_scope_and_frozen_evidence(self) -> None:
        frozen = await self.freeze()
        self.assertEqual(frozen['platform']['priceVersionId'], self.price_id)
        self.assertEqual(frozen['procurement']['currency'], 'USD')
        self.assertEqual(frozen['platform']['sourceIds'], [self.source_id])
        with self.assertRaises(ServiceWarning):
            await self.freeze(account_id=999999)
        with self.assertRaises(ServiceWarning):
            await self.freeze(at='2026-12-31T23:59:59+00:00')
        next_id = await self.draft()
        await self.publish(
            next_id,
            start='2027-02-01T00:00:00Z',
            replaceActivationId=frozen['platform']['activationId'],
            expectedActivationRevision='1',
        )
        switched = await self.freeze(at='2027-02-01T00:00:00+00:00')
        self.assertEqual(switched['platform']['priceVersionId'], next_id)
        self.assertIsNone(frozen['platform']['effectiveUntil'])
        previous = await self.freeze(at='2027-01-31T23:59:59+00:00')
        self.assertEqual(previous['platform']['priceVersionId'], self.price_id)

    async def test_missing_currency_and_activation_overlap_rejected(self) -> None:
        async with self.sessions() as db:
            with self.assertRaises(ValueError):
                await GenerationPriceService.freeze(
                    db,
                    variant_id=int(self.variant_id),
                    account_id=int(self.account_id),
                    currencies={'platform': 'CNY'},
                    at=datetime.now(timezone.utc),
                )
            await db.execute(
                text(
                    'INSERT INTO hf_price_activation(price_book_id,price_version_id,effective_from,create_time,update_time) SELECT price_book_id,price_version_id,effective_from,NOW(),NOW() FROM hf_price_activation WHERE price_version_id=:v'
                ),
                {'v': int(self.price_id)},
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.freeze()

    async def test_procurement_only_uses_exact_scope_and_half_open_interval(self):
        at = datetime.fromisoformat('2027-01-01T00:00:00+00:00')
        async with self.sessions() as db:
            async def freeze(**changes):
                values = dict(variant_id=int(self.variant_id), account_id=int(self.account_id), currency='USD', at=at)
                return await GenerationPriceService.freeze_procurement(db, **(values | changes))
            result = await freeze()
            self.assertEqual(result['currency'], 'USD')
            self.assertEqual(result['accountId'], self.account_id)
            self.assertTrue(result['items'])
            self.assertEqual(result['sourceIds'], [self.source_id])
            for changes in ({'currency': 'CNY'}, {'account_id': 999999}, {'variant_id': 999999},
                            {'at': datetime.fromisoformat('2026-12-31T23:59:59+00:00')}):
                with self.assertRaises(ServiceWarning):
                    await freeze(**changes)
            for changes in ({'currency': ''}, {'currency': 'usd'}, {'at': datetime(2027, 1, 1)}):
                with self.assertRaises(ValueError):
                    await freeze(**changes)
            await db.execute(text("UPDATE hf_price_activation SET effective_until='2027-02-01T00:00:00Z' WHERE activation_id=:id"),
                {'id': int(result['activationId'])})
            await db.commit()
            self.assertIsNone(result['effectiveUntil'])
            with self.assertRaises(ServiceWarning):
                await freeze(at=datetime.fromisoformat('2027-02-01T00:00:00+00:00'))

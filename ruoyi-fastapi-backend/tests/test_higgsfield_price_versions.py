"""价格草稿聚合保存、并发版本与已发布不可变约束。"""

import os
import asyncio
import unittest
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.price_version_vo import (
    PriceVersionCreate,
    PriceVersionPatch,
    PriceVersionQuery,
    PriceItemInput,
)
from module_higgsfield.entity.vo.price_vo import PriceBookCreate, PriceSourceCreate
from module_higgsfield.service.price_service import PriceService
from module_higgsfield.service.price_source_service import PriceSourceService
from module_higgsfield.service.price_version_service import PriceVersionService
from tests import test_higgsfield_price_sources as sources


def rule(**changes):
    return (
        dict(
            itemCode='video_tokens',
            unit='token',
            unitQuantity='1000000',
            unitPrice='70',
            quantityFrom='0',
            formulaTemplate='linear',
        )
        | changes
    )


class VersionInputTests(unittest.TestCase):
    def test_precise_input_and_patch_contract(self):
        for changes in (
            {'unitPrice': 0.1},
            {'unitPrice': '1e3'},
            {'unitPrice': '0.00000000001'},
            {'unitQuantity': '0'},
            {'quantityTo': '0'},
            {'unitPrice': '0'},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                PriceItemInput(**rule(**changes))
        for values in ({'revision': '1'}, {'revision': '1', 'items': None}, {'revision': '1', 'sourceIds': ['1', '1']}):
            with self.assertRaises(ValidationError):
                PriceVersionPatch(**values)
        self.assertEqual(PriceVersionPatch(revision='1', items=[]).items, [])


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceVersionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = sources.PriceSourceTests.cleanup_schema

    async def asyncSetUp(self):
        await sources.PriceSourceTests.asyncSetUp(self)
        async with self.sessions() as db:
            book, _ = await PriceService.create(
                db,
                self.owner,
                PriceBookCreate(modelVariantId=self.variant_id, purpose='platform', currency='CNY', name='版本测试'),
                str(uuid4()),
            )
            self.book_id = book['data']['id']
            source, _ = await PriceSourceService.create(
                db,
                self.owner,
                PriceSourceCreate(
                    sourceType='manual_confirmation', excerpt='测试单价依据', observedAt='2026-01-01T00:00:00Z'
                ),
                str(uuid4()),
            )
            self.source_id = source['data']['id']

    def payload(self, **changes):
        return PriceVersionCreate(
            **(
                dict(
                    priceBookId=self.book_id,
                    roundingMode='half_up',
                    calculationScale=10,
                    items=[rule()],
                    sourceIds=[self.source_id],
                )
                | changes
            )
        )

    async def save(self, payload, key=None, identity=None):
        async with self.sessions() as db:
            return await PriceVersionService.save(db, self.owner, payload, key or str(uuid4()), identity)

    async def test_incomplete_draft_edit_replay_and_cas(self):
        result, _ = await self.save(self.payload(items=[], sourceIds=[]))
        draft = result['data']
        self.assertEqual(len(draft['validationIssues']), 2)
        key = str(uuid4())
        patch = PriceVersionPatch(revision='1', items=[rule()], sourceIds=[self.source_id])
        updated, _ = await self.save(patch, key, draft['id'])
        repeated, replay = await self.save(patch, key, draft['id'])
        self.assertTrue(replay)
        self.assertEqual(updated, repeated)
        self.assertEqual(updated['data']['validationIssues'], [])
        self.assertEqual(updated['data']['revision'], '2')
        with self.assertRaises(ServiceWarning):
            await self.save(patch, identity=draft['id'])
        async with self.sessions() as db:
            page = await PriceVersionService.listing(
                db, self.owner, PriceVersionQuery(priceBookId=self.book_id, status='draft')
            )
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['revision'], '2')
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='price_version'")), 2
            )

    async def test_invalid_source_rolls_back_and_published_refuses_edit(self):
        result, _ = await self.save(self.payload())
        identity = result['data']['id']
        with self.assertRaises(ServiceWarning):
            await self.save(
                PriceVersionPatch(revision='1', items=[], sourceIds=['9223372036854775807']), identity=identity
            )
        async with self.sessions() as db:
            unchanged = await PriceVersionService.get(db, self.owner, identity)
            self.assertEqual(unchanged, result['data'])
            # 仅模拟发布状态验证编辑防线，不冒充已执行发布流程。
            await db.execute(
                text("UPDATE hf_price_version SET status='1' WHERE price_version_id=:id"), {'id': int(identity)}
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.save(PriceVersionPatch(revision='1', items=[]), identity=identity)
        next_result, _ = await self.save(self.payload())
        self.assertEqual(next_result['data']['versionNo'], 2)

    async def test_parallel_version_numbers_and_single_revision_winner(self):
        results = await asyncio.gather(self.save(self.payload()), self.save(self.payload()))
        self.assertEqual(sorted(result[0]['data']['versionNo'] for result in results), [1, 2])
        identity = results[0][0]['data']['id']
        outcomes = await asyncio.gather(
            self.save(PriceVersionPatch(revision='1', calculationScale=8), identity=identity),
            self.save(PriceVersionPatch(revision='1', calculationScale=9), identity=identity),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(outcome, ServiceWarning) for outcome in outcomes), 1)
        self.assertEqual(sum(isinstance(outcome, tuple) for outcome in outcomes), 1)

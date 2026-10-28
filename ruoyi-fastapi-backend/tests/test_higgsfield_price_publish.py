"""价格发布并发、替换回滚与区间历史的隔离数据库验证。"""

import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from unittest.mock import patch
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.price_publish_vo import PricePublish, PriceActivationEnd, PriceHistoryQuery
from module_higgsfield.service.price_publish_service import PricePublishService
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.dao.price_publish_dao import PricePublishDao
from module_higgsfield.entity.do.price_do import HfPriceActivation
from tests import test_higgsfield_price_versions as versions


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PricePublishTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = versions.PriceVersionTests.cleanup_schema
    payload = versions.PriceVersionTests.payload
    save = versions.PriceVersionTests.save

    async def asyncSetUp(self):
        await versions.PriceVersionTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'publish_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_25_price_publish.py'
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:

            def execute(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(execute)
            # 仅准备已发布能力用于价格事务测试，不代表供应商联调。
            await conn.execute(
                text("UPDATE hf_model_profile_version SET status='2' WHERE model_id=:id"), {'id': int(self.model_id)}
            )

    async def draft(self, **changes):
        result, _ = await self.save(self.payload(**changes))
        return result['data']['id']

    async def publish(self, identity, start='2027-01-01T00:00:00Z', key=None, **changes):
        payload = PricePublish(**(dict(revision='1', effectiveFrom=start, reason='测试价格发布') | changes))
        async with self.sessions() as db:
            return await PricePublishService.publish(db, self.owner, identity, payload, key or str(uuid4()))

    async def test_publish_replay_replace_and_end_history(self):
        first = await self.draft()
        key = str(uuid4())
        result, _ = await self.publish(first, key=key)
        repeated, replay = await self.publish(first, key=key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        self.assertEqual(result['data']['version']['status'], 'published')
        old = result['data']['activation']
        second = await self.draft()
        replacement, _ = await self.publish(
            second, start='2027-02-01T00:00:00Z', replaceActivationId=old['id'], expectedActivationRevision='1'
        )
        new = replacement['data']['activation']
        async with self.sessions() as db:
            history = await PricePublishService.history(db, self.owner, first, PriceHistoryQuery())
            self.assertEqual(history.total, 2)
            self.assertEqual(history.rows[0]['diff']['after']['effectiveUntil'], new['effectiveFrom'])
            ended, _ = await PricePublishService.end(
                db,
                self.owner,
                new['id'],
                PriceActivationEnd(revision='1', effectiveUntil='2027-03-01T00:00:00Z', reason='停止使用'),
                str(uuid4()),
            )
            self.assertEqual(ended['data']['revision'], '2')
        third = await self.draft()
        await self.publish(third, start='2027-03-01T00:00:00Z')

    async def test_overlap_concurrency_and_failed_replacement_rolls_back(self):
        first, second = await self.draft(), await self.draft()
        outcomes = await asyncio.gather(self.publish(first), self.publish(second), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in outcomes), 1)
        successful = next(value[0]['data'] for value in outcomes if isinstance(value, tuple))
        loser = second if successful['version']['id'] == first else first
        with self.assertRaises(ServiceWarning):
            await self.publish(
                loser,
                start='2027-02-01T00:00:00Z',
                replaceActivationId=successful['activation']['id'],
                expectedActivationRevision='2',
            )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_activation')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_publish_event')), 1)
            self.assertIsNone(await db.scalar(text('SELECT effective_until FROM hf_price_activation')))
            draft = await PriceVersionService.get(db, self.owner, loser)
            self.assertEqual(draft['status'], 'draft')
            self.assertEqual(draft['revision'], '1')

    async def test_incomplete_and_unpublished_model_rejected(self):
        incomplete = await self.draft(sourceIds=[])
        with self.assertRaises(ServiceWarning):
            await self.publish(incomplete)
        complete = await self.draft()
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_model_profile_version SET status='0' WHERE model_id=:id"), {'id': int(self.model_id)}
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.publish(complete)

    async def test_failure_after_old_interval_write_rolls_back_everything(self):
        first, second = await self.draft(), await self.draft()
        result, _ = await self.publish(first)
        original = PricePublishDao.add

        async def fail_activation(db, model, **values):
            if model is HfPriceActivation:
                raise RuntimeError('模拟新生效区间写入失败')
            return await original(db, model, **values)

        with patch.object(PricePublishDao, 'add', side_effect=fail_activation), self.assertRaises(RuntimeError):
            await self.publish(
                second,
                start='2027-02-01T00:00:00Z',
                replaceActivationId=result['data']['activation']['id'],
                expectedActivationRevision='1',
            )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_publish_event')), 1)
            self.assertIsNone(await db.scalar(text('SELECT effective_until FROM hf_price_activation')))
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_price_activation')), 1)
            draft = await PriceVersionService.get(db, self.owner, second)
            self.assertEqual((draft['status'], draft['revision']), ('draft', '1'))

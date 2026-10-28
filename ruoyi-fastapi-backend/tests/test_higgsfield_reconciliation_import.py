"""真实数据库导入的原子性、跨文件去重和冲突传播。"""
import asyncio
import os
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationBatch
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.service.reconciliation_import_service import ReconciliationImportService as Import
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService as Parser
from tests import test_higgsfield_reconciliation_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationImportTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.ReconciliationStorageTests.cleanup_schema
    migrate = storage.ReconciliationStorageTests.migrate

    async def asyncSetUp(self):
        await storage.ReconciliationStorageTests.asyncSetUp(self)
        self.counter = 0

    async def batch(self, account=1):
        self.counter += 1
        async with self.sessions() as db:
            batch = await Dao.add(db, HfReconciliationBatch, account_id=account,
                period_start=self.audit['create_time'], period_end=self.audit['create_time']+timedelta(days=1),
                source_file_id=self.counter, file_hash=f'{self.counter:064x}', **self.audit)
            await db.commit()
            return batch.batch_id

    def rows(self, amount='1.25', currency='USD'):
        return Parser.csv(f'externalLineKey,currency,amount\n0001,{currency},{amount}\n'.encode(), 4096)

    async def apply(self, batch, rows=None):
        async with self.sessions() as db:
            return await Import.apply(db, batch, self.rows() if rows is None else rows)

    async def test_duplicates_conflicts_and_original_amount(self):
        first, repeated, changed = await self.batch(), await self.batch(), await self.batch()
        self.assertTrue(await self.apply(first))
        self.assertFalse(await self.apply(first))
        self.assertTrue(await self.apply(repeated, self.rows('1.2500')))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_line')), 1)
            await db.execute(text("UPDATE hf_reconciliation_line SET subject_id=12,status='2'"))
            await db.execute(text("UPDATE hf_reconciliation_batch SET status='2' WHERE batch_id=:id"), {'id': first})
            await db.commit()
        self.assertTrue(await self.apply(changed, self.rows('-0.0000000001')))
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT amount,status,revision,subject_id FROM hf_reconciliation_line'))).one()
            self.assertEqual(tuple(row), (Decimal('1.25'), '3', 2, 12))
            statuses = (await db.execute(text('SELECT status FROM hf_reconciliation_batch ORDER BY batch_id'))).scalars().all()
            self.assertEqual(statuses, ['3', '3', '3'])
            outcomes = (await db.execute(text('SELECT outcome FROM hf_reconciliation_observation ORDER BY observation_id'))).scalars().all()
            self.assertEqual(outcomes, ['original', 'duplicate', 'conflict'])
            raw = await db.scalar(text("SELECT raw_line->>'amount' FROM hf_reconciliation_observation WHERE outcome='conflict'"))
            self.assertEqual(raw, '-0.0000000001')
        with self.assertRaises(ServiceWarning):
            await self.apply(first, self.rows('9'))
        another = await self.batch()
        await self.apply(another, self.rows('8'))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_reconciliation_line')), 3)
            self.assertEqual(await db.scalar(text('SELECT amount FROM hf_reconciliation_line')), Decimal('1.25'))

    async def test_concurrent_same_account_and_separate_accounts(self):
        one, two = await self.batch(), await self.batch()
        self.assertEqual(await asyncio.gather(self.apply(one), self.apply(two)), [True, True])
        other = await self.batch(account=2)
        await self.apply(other, self.rows('8'))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_line')), 2)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_reconciliation_observation WHERE outcome='duplicate'")), 1)

    async def test_duplicate_confirmed_batch_and_mixed_new_items(self):
        first = await self.batch()
        await self.apply(first)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_reconciliation_line SET subject_id=12,status='2',revision=3"))
            await db.execute(text("UPDATE hf_reconciliation_batch SET status='2'"))
            await db.commit()
        duplicate = await self.batch()
        await self.apply(duplicate, self.rows('1.2500'))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch WHERE batch_id=:id'),
                {'id': duplicate}), '2')
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_reconciliation_line')), 3)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_line')), 1)
        mixed = await self.batch()
        rows = Parser.csv(b'externalLineKey,currency,amount\n0001,USD,1.25\nnew,USD,2\n', 4096)
        await self.apply(mixed, rows)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch WHERE batch_id=:id'),
                {'id': mixed}), '1')
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch WHERE batch_id=:id'),
                {'id': duplicate}), '2')
        self.assertFalse(await self.apply(duplicate, self.rows('1.2500')))

    async def test_partial_failure_rolls_back_then_retry(self):
        batch = await self.batch()
        rows = Parser.csv(b'externalLineKey,currency,amount\na,USD,1\nb,USD,2\n', 4096)
        original = Dao.add
        calls = 0
        async def failing(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('模拟中途失败')
            return await original(*args, **kwargs)
        with patch.object(Dao, 'add', side_effect=failing):
            with self.assertRaises(OSError):
                await self.apply(batch, rows)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_line')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_observation')), 0)
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch')), '0')
        self.assertTrue(await self.apply(batch, rows))
        self.assertFalse(await self.apply(batch, rows))

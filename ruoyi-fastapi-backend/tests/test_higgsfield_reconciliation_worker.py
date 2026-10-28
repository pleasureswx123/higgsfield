"""从真实管理上传到对账处理的本地文件及 PostgreSQL 验证。"""
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from dataclasses import replace
from tests import test_higgsfield_reconciliation_parser as parser_tests
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService as Parser
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.service.reconciliation_service import ReconciliationService
from module_higgsfield.service.reconciliation_worker_service import ReconciliationWorker
from tests import test_higgsfield_reconciliation_requests as requests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationWorkerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = requests.ReconciliationRequestTests.cleanup_schema
    upload = requests.ReconciliationRequestTests.upload
    payload = requests.ReconciliationRequestTests.payload

    async def asyncSetUp(self):
        await requests.ReconciliationRequestTests.asyncSetUp(self)
        self.worker = ReconciliationWorker(self.sessions, self.storage, concurrency=2)

    async def submit(self):
        identity = await self.upload(purpose='reconciliation')
        async with self.sessions() as db:
            response, _ = await ReconciliationService.create(db, self.owner, self.payload(identity), str(uuid4()))
            return int(response['data']['id'])

    async def test_real_file_import_and_concurrent_repeat(self):
        identity = await self.submit()
        results = await asyncio.gather(self.worker.execute(identity), self.worker.execute(identity))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(await self.worker.run_once(), [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch')), '1')
            self.assertIsNone(await db.scalar(text('SELECT import_error FROM hf_reconciliation_batch')))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_observation')), 1)
            detail = await ReconciliationService.get(db, self.owner, identity)
            self.assertEqual(detail['importState'], 'processed')
            self.assertEqual(detail['counts'], {'total': 1, 'matched': 0, 'disputed': 0})
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await ReconciliationService.get(db, self.owner, identity)

    async def test_xlsx_upload_import_and_download(self):
        self.storage.policy = replace(self.storage.policy, max_bytes=65536)
        self.body = parser_tests.ReconciliationParserTests.workbook([['000123', 'USD', '0.0000000001']])
        upload = await self.upload(purpose='reconciliation', mime=Parser.xlsx_mime, name='供应商账单.xlsx')
        async with self.sessions() as db:
            receipt, _ = await ReconciliationService.create(db, self.owner, self.payload(upload), str(uuid4()))
            identity = int(receipt['data']['id'])
        self.assertTrue(await self.worker.execute(identity))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT external_line_key FROM hf_reconciliation_line')), '000123')
            self.assertEqual(await db.scalar(text("SELECT raw_line->>'amount' FROM hf_reconciliation_line")), '0.0000000001')
            detail = await ReconciliationService.get(db, self.owner, identity)
            self.assertEqual(detail['attachment']['mimeType'], Parser.xlsx_mime)
            stream, _, mime, _ = await ReconciliationService.download(db, self.owner, identity, storage=self.storage)
            self.assertEqual(mime, Parser.xlsx_mime)
            self.assertEqual(b''.join([chunk async for chunk in stream]), self.body)

    async def test_bad_template_and_corrupted_file_are_terminal(self):
        self.body = b'wrongHeader,currency,amount\nkey,USD,1.25\n'
        bad_template = await self.submit()
        self.body = b'externalLineKey,currency,amount\nkey,USD,1.25\n'
        corrupted = await self.submit()
        async with self.sessions() as db:
            key = await db.scalar(text('SELECT storage_key FROM hf_stored_file f JOIN hf_reconciliation_batch b ON b.source_file_id=f.file_id WHERE b.batch_id=:id'), {'id': corrupted})
        path = Path(self.storage.policy.root) / key
        path.write_bytes(b'x' * len(self.body))
        await self.worker.run_once()
        async with self.sessions() as db:
            rows = (await db.execute(text('SELECT batch_id,status,import_error FROM hf_reconciliation_batch ORDER BY batch_id'))).all()
            self.assertEqual([row.status for row in rows], ['3', '3'])
            self.assertEqual(rows[0].import_error['lineNo'], 1)
            self.assertEqual(rows[1].import_error['lineNo'], 0)
            self.assertNotIn('wrongHeader', str(rows))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_reconciliation_line')), 0)
            detail = await ReconciliationService.get(db, self.owner, bad_template)
            self.assertEqual(detail['importState'], 'failed')
            self.assertEqual(detail['importError']['lineNo'], 1)
        self.assertFalse(await self.worker.execute(bad_template))
        self.assertFalse(await self.worker.execute(corrupted))

    async def test_storage_unavailable_can_recover(self):
        identity = await self.submit()
        with patch.object(self.storage, 'open_key', side_effect=ServiceWarning(
                message='模拟存储暂时不可用', data={'errorCode': 'STORAGE_UNAVAILABLE'})):
            results = await self.worker.run_once()
        self.assertEqual(results[0]['status'], 'failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch')), '0')
            self.assertIsNone(await db.scalar(text('SELECT import_error FROM hf_reconciliation_batch')))
        self.assertTrue(await self.worker.execute(identity))

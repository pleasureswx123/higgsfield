"""原始账单授权下载、范围读取和证据关联校验。"""
import os
import unittest
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.service.reconciliation_service import ReconciliationService as Service
from tests import test_higgsfield_reconciliation_worker as worker


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationAttachmentTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.ReconciliationWorkerTests.cleanup_schema
    upload = worker.ReconciliationWorkerTests.upload
    payload = worker.ReconciliationWorkerTests.payload
    submit = worker.ReconciliationWorkerTests.submit

    async def asyncSetUp(self):
        await worker.ReconciliationWorkerTests.asyncSetUp(self)
        self.batch_id = await self.submit()

    async def test_original_range_head_and_revocation(self):
        async with self.sessions() as db:
            detail = await Service.get(db, self.owner, self.batch_id)
            self.assertEqual(detail['attachment']['byteSize'], str(len(self.body)))
            self.assertNotIn('storage_key', str(detail))
            body, headers, mime, status = await Service.download(db, self.owner, self.batch_id, storage=self.storage)
            self.assertEqual(status, 200)
            self.assertEqual(mime, 'text/csv')
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertIn('attachment', headers['Content-Disposition'])
            self.assertEqual(b''.join([part async for part in body]), self.body)
            body, headers, _, status = await Service.download(db, self.owner, self.batch_id,
                'bytes=0-3', storage=self.storage)
            self.assertEqual(status, 206)
            self.assertEqual(b''.join([part async for part in body]), self.body[:4])
            body, _, _, status = await Service.download(db, self.owner, self.batch_id,
                head=True, storage=self.storage)
            self.assertIsNone(body)
            self.assertEqual(status, 200)
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await Service.download(db, self.owner, self.batch_id, storage=self.storage)

    async def test_mismatched_binding_refused_without_losing_diagnostics(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_reconciliation_batch SET file_hash=:hash WHERE batch_id=:id"),
                {'hash': '0'*64, 'id': self.batch_id})
            await db.commit()
            detail = await Service.get(db, self.owner, self.batch_id)
            self.assertIsNone(detail['attachment'])
            self.assertEqual(detail['importState'], 'pending')
            with self.assertRaises(ServiceWarning) as caught:
                await Service.download(db, self.owner, self.batch_id, storage=self.storage)
            self.assertEqual(caught.exception.data['errorCode'], 'FILE_NOT_READY')

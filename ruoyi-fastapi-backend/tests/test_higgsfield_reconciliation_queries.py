"""对账列表先筛选后分页，重复与冲突观察不覆盖正式金额。"""
import os
import unittest
from pydantic import ValidationError
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.reconciliation_vo import ReconciliationQuery, ReconciliationLineQuery
from module_higgsfield.service.reconciliation_service import ReconciliationService as Service
from tests import test_higgsfield_reconciliation_worker as worker


class ReconciliationQueryInputTests(unittest.TestCase):
    def test_bounded_page_and_status(self):
        for model in (ReconciliationQuery, ReconciliationLineQuery):
            for fields in ({'pageSize': 101}, {'pageNum': 0}, {'status': 'unknown'}):
                with self.assertRaises(ValidationError):
                    model(**fields)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationQueryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.ReconciliationWorkerTests.cleanup_schema
    upload = worker.ReconciliationWorkerTests.upload
    payload = worker.ReconciliationWorkerTests.payload
    submit = worker.ReconciliationWorkerTests.submit

    async def asyncSetUp(self):
        await worker.ReconciliationWorkerTests.asyncSetUp(self)

    async def test_filter_pagination_evidence_and_permission(self):
        self.body = b'externalLineKey,currency,amount\na,USD,1\na,USD,1.00\n'
        original = await self.submit()
        await self.worker.execute(original)
        self.body = b'externalLineKey,currency,amount\na,USD,2\nb,USD,5\n'
        revised = await self.submit()
        await self.worker.execute(revised)
        self.body = b'externalLineKey,currency,amount\nc,USD,3\n'
        pending = await self.submit()
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, ReconciliationQuery(pageSize=1))
            self.assertEqual(page.total, 3)
            self.assertTrue(page.has_next if hasattr(page, 'has_next') else page.hasNext)
            self.assertEqual(page.rows[0]['id'], str(pending))
            page = await Service.listing(db, self.owner, ReconciliationQuery(status='disputed', pageSize=1, pageNum=2))
            self.assertEqual(page.total, 2)
            self.assertEqual(page.rows[0]['id'], str(original))
            self.assertEqual(page.rows[0]['counts'], {'total': 2, 'matched': 0, 'disputed': 2})
            self.assertEqual((await Service.listing(db, self.owner, ReconciliationQuery(accountId='999999'))).total, 0)
            lines = await Service.lines(db, self.owner, revised, ReconciliationLineQuery(status='disputed'))
            self.assertEqual(lines.total, 1)
            row = lines.rows[0]
            self.assertEqual(row['amount'], '1.0000000000')
            self.assertEqual(row['sourceEvidence']['amount'], '2')
            self.assertEqual(row['outcome'], 'conflict')
            self.assertEqual(row['canonicalBatchId'], str(original))
            unmatched = await Service.lines(db, self.owner, revised, ReconciliationLineQuery(status='unmatched'))
            self.assertEqual(unmatched.total, 1)
            self.assertEqual(unmatched.rows[0]['externalLineKey'], 'b')
            repeated = await Service.lines(db, self.owner, original, ReconciliationLineQuery())
            self.assertEqual(repeated.rows[0]['id'], repeated.rows[1]['id'])
            self.assertNotEqual(repeated.rows[0]['observationId'], repeated.rows[1]['observationId'])
            self.assertEqual([row['lineNo'] for row in repeated.rows], [2, 3])
            with self.assertRaises(ServiceWarning):
                await Service.lines(db, self.owner, 999999, ReconciliationLineQuery())
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await Service.listing(db, self.owner, ReconciliationQuery())
            with self.assertRaises(PermissionException):
                await Service.lines(db, self.owner, original, ReconciliationLineQuery())

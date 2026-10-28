"""同一隔离图片任务贯通生成、归档、两口径计价与预算结算，不调用真实供应商。"""
import importlib.util
import os
import unittest
from decimal import Decimal
from pathlib import Path
from sqlalchemy import text

from module_higgsfield.service.billing_worker_service import BillingWorker
from tests import test_higgsfield_image_submit_handler as image


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ImageBillingFlowTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = image.ImageSubmitHandlerTests.cleanup_schema
    migrate = image.ImageSubmitHandlerTests.migrate
    job = image.ImageSubmitHandlerTests.job
    close_server = image.ImageSubmitHandlerTests.close_server
    respond = image.ImageSubmitHandlerTests.respond

    async def asyncSetUp(self):
        await image.ImageSubmitHandlerTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('flow_billing',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_39_billing_facts.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        # 基础夹具已建立6元预占。此处仅配置测试图片单价；进入执行后不再改变固定价格。
        # 这验证已受理任务的跨模块执行，不替代前端估价及发布价格的验收。
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_price_rule_item r SET item_code='input',unit_quantity=1, "
                "unit_price=CASE WHEN b.purpose='platform' THEN 0.1 ELSE 0.2 END "
                "FROM hf_price_version v JOIN hf_price_book b ON b.price_book_id=v.price_book_id "
                "WHERE r.price_version_id=v.price_version_id"))
            await db.commit()

    async def test_same_job_archives_and_settles_once_with_distinct_currencies(self):
        identity = self.lease.job_id
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), Decimal('6'))
        # 真实HTTP回环响应和图片落盘，随后消费同一任务的持久化用量。
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        billing = BillingWorker(self.sessions, 'image-flow-billing')
        self.assertEqual((await billing.process(identity))['status'], 'handled')
        async with self.sessions() as db:
            rows = (await db.execute(text('SELECT purpose,currency,amount FROM hf_billing_event ORDER BY purpose'))).all()
            self.assertEqual([tuple(row) for row in rows], [
                ('platform', 'CNY', Decimal('1.2')), ('procurement', 'USD', Decimal('2.4'))])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject WHERE job_id=:id'), {'id': identity}), 1)
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output WHERE job_id=:id'), {'id': identity}), '2')
            self.assertEqual((await db.execute(text('SELECT reserved_amount,consumed_amount FROM hf_budget_period'))).one(),
                             (Decimal('0'), Decimal('1.2')))
            self.assertEqual((await db.execute(text('SELECT sum(reserved_delta),sum(consumed_delta) FROM hf_budget_ledger_entry'))).one(),
                             (Decimal('0'), Decimal('1.2')))
            before = (await db.execute(text('SELECT to_jsonb(e) FROM hf_budget_ledger_entry e ORDER BY entry_id'))).all()
            key = await db.scalar(text('SELECT storage_key FROM hf_stored_file'))
        self.assertEqual((Path(self.temp.name) / key).read_bytes(), self.data)
        self.assertEqual(await self.worker.run_once(), [])
        self.assertEqual((await billing.process(identity))['status'], 'skipped')
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT to_jsonb(e) FROM hf_budget_ledger_entry e ORDER BY entry_id'))).all(), before)

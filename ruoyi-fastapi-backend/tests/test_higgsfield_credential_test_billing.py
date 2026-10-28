"""测试采购快照、实际用量及金额在真实隔离数据库中闭环验证。"""
import importlib.util
import os
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from tests import test_higgsfield_credential_test_executor as executors
from tests import test_higgsfield_credential_image_probe as probes
from module_higgsfield.entity.do.model_do import HfModelVariant
from module_higgsfield.entity.do.price_do import HfPriceBook, HfPriceVersion, HfPriceRuleItem, HfPriceSource, HfPriceVersionSource, HfPriceActivation
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.credential_test_billing_service import CredentialTestBillingService
from module_higgsfield.service.credential_test_usage_service import CredentialTestUsageService
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService
from module_higgsfield.service.credential_test_service import CredentialTestService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestBillingTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def asyncSetUp(self):
        await executors.CredentialTestExecutorTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            for name in ('20261027_22_prices.py', '20261027_24_price_sources.py', '20261027_25_price_publish.py'):
                spec = importlib.util.spec_from_file_location('test_billing_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
        async with self.sessions() as db:
            async def add(row):
                db.add(row)
                await db.flush()
                return row
            now = await JobLeaseDao.now(db)
            variant = await add(HfModelVariant(model_version_id=self.model_version_id, variant_key='empty', dimensions={}))
            book = await add(HfPriceBook(model_variant_id=variant.variant_id, account_id=int(self.account_id), purpose='procurement', currency='USD', price_book_name='测试采购'))
            version = await add(HfPriceVersion(price_book_id=book.price_book_id, version_no=1, status='1', rounding_mode='half_up', calculation_scale=6, create_user_id=1))
            for code, price in (('input', '1.2'), ('output', '2.3')):
                await add(HfPriceRuleItem(price_version_id=version.price_version_id, item_code=code, unit='token', unit_quantity=Decimal('1000'), unit_price=Decimal(price), formula_template='linear'))
            source = await add(HfPriceSource(source_type='manual_confirmation', excerpt='隔离测试价格证据', observed_time=now, create_user_id=1))
            await add(HfPriceVersionSource(price_version_id=version.price_version_id, source_id=source.source_id))
            await add(HfPriceActivation(price_book_id=book.price_book_id, price_version_id=version.price_version_id, effective_from=now-timedelta(days=1)))
            await db.commit()
        self.executor.procurement_currency = 'USD'

    async def test_exact_amount_idempotence_and_conflicting_usage_preserves_amount(self):
        self.response = probes.CredentialImageProbeTests().response(usage={'input_tokens': 100, 'output_tokens': 200})
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        self.assertTrue(await self.executor.execute(identity))
        self.assertFalse(await self.executor.execute(identity))
        async with self.sessions() as db:
            event = (await db.execute(text('SELECT * FROM hf_billing_event'))).mappings().one()
            self.assertEqual(event['amount'], Decimal('0.58'))
            self.assertEqual(event['purpose'], 'procurement')
            self.assertEqual(event['state'], '1')
            detail = await CredentialTestService.get(db, self.owner, identity)
            self.assertEqual(detail['costVisibility'], 'visible')
            self.assertEqual(detail['cost']['effectiveAmount'], '0.5800000000')
            self.assertEqual(detail['cost']['currency'], 'USD')
            self.owner.permissions = ['credential:read']
            hidden = await CredentialTestService.get(db, self.owner, identity)
            self.assertEqual(hidden['costVisibility'], 'hidden')
            self.assertNotIn('cost', hidden)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_line_item')), 2)
            test = await CredentialTestDao.locked(db, identity)
            call = await ProviderCallDao.locked(db, test.provider_call_id)
            now = await JobLeaseDao.now(db)
            _, changed = await CredentialTestBillingService.calculate(db, test, call, now=now)
            self.assertFalse(changed)
            await CredentialTestUsageService.append(db, test, call,
                UsageNormalizationService.image({'input_tokens': 100, 'output_tokens': 300}), now=now)
            disputed, changed = await CredentialTestBillingService.calculate(db, test, call, now=now)
            self.assertTrue(changed)
            self.assertEqual(disputed.state, '3')
            self.assertEqual(disputed.amount, Decimal('0.58'))
            await db.commit()
        self.assertEqual(self.calls, 1)

    async def test_unknown_usage_keeps_pending_amount_null(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        await self.executor.execute(int(receipt['data']['id']))
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT * FROM hf_billing_event'))).mappings().one()
            self.assertEqual(row['state'], '0')
            self.assertIsNone(row['amount'])
            detail = await CredentialTestService.get(db, self.owner, int(receipt['data']['id']))
            self.assertEqual(detail['cost']['state'], 'pending')
            self.assertIsNone(detail['cost']['amount'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_line_item')), 0)

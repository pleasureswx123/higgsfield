"""隔离数据库与真实加密文件验证测试执行，传输使用模拟响应。"""
import asyncio
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from tests import test_higgsfield_credential_test_requests as requests
from tests import test_higgsfield_credential_image_probe as probes
from module_higgsfield.entity.do.model_do import HfModelProfile, HfModelProfileVersion
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.credential_test_executor_service import CredentialTestExecutorService
from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
from module_higgsfield.service.credential_test_response_service import CredentialTestResponseService
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.provider_http_service import ProviderHttpResult
from module_higgsfield.service.storage_service import StorageService, StoragePolicy


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestExecutorTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = requests.CredentialTestRequestTests.cleanup_schema
    payload = requests.CredentialTestRequestTests.payload
    save = requests.CredentialTestRequestTests.save
    request = requests.CredentialTestRequestTests.request

    async def asyncSetUp(self):
        await requests.CredentialTestRequestTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location('test_response_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_59_credential_test_responses.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade()
            await conn.run_sync(migrate)
        async with self.sessions() as db:
            connection_id = await db.scalar(text('SELECT connection_id FROM hf_provider_account LIMIT 1'))
            model = HfModelProfile(connection_id=connection_id, code='probe', display_name='测试图片', kind='image')
            db.add(model)
            await db.flush()
            version = HfModelProfileVersion(model_id=model.model_id, version_no=1, gateway_alias='probe-image',
                region='eva', capabilities={'parametersSchema': {'properties': {}}, 'referenceRules': {'maxTotal': 0}})
            db.add(version)
            await db.flush()
            self.model_version_id = version.model_version_id
            await db.commit()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 2000000, 1000))
        self.keyring = CredentialKeyring('v1', {'v1': b'a'*32}, b'b'*32)
        self.evidence = ProviderResponseStorageService(self.storage, CredentialTestResponseCryptoService(self.keyring), max_bytes=1100000)
        self.calls = 0
        self.response = probes.CredentialImageProbeTests().response()
        self.cancel = False
        parent = self
        class Transport:
            async def submit(self, payload):
                parent.calls += 1
                # 独立会话能读取已提交意图，证明发送前已完成事务提交。
                async with parent.sessions() as db:
                    parent.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE state='1'")), 1)
                if parent.cancel:
                    raise asyncio.CancelledError()
                return parent.response
        self.executor = CredentialTestExecutorService(self.sessions, self.storage, self.evidence,
            max_decoded_bytes=10000, transport_factory=lambda binding: Transport())

    async def test_success_evidence_encryption_and_no_duplicate_send(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        self.assertTrue(await self.executor.execute(identity))
        self.assertFalse(await self.executor.execute(identity))
        self.assertEqual(self.calls, 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_test')), '1')
            evidence = (await db.execute(text('SELECT * FROM hf_credential_test_response'))).mappings().one()
            facts = {key: evidence[key] for key in ('storage_key', 'sha256', 'byte_size')}
            self.assertEqual(await self.evidence.load(facts, evidence['provider_call_id'], identity), self.response.body)
            with self.storage.open_key(facts['storage_key']) as handle:
                encrypted = handle.read()
            self.assertNotIn(b'probe-1', encrypted)
            with self.assertRaises(ValueError):
                ProviderResponseCryptoService(self.keyring).decrypt(encrypted, evidence['provider_call_id'], identity)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_credential_test_response'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_credential_test_response'::regclass AND contype='f'")), 0)
            await db.rollback()
            self.assertEqual(await CredentialTestResponseService.register(db, identity, evidence['provider_call_id'], facts,
                http_status=200), evidence['response_evidence_id'])
            with self.assertRaises(ValueError):
                await CredentialTestResponseService.register(db, identity, evidence['provider_call_id'],
                    facts | {'sha256': 'a'*64}, http_status=200)

    async def test_timeout_keeps_unknown_and_unsupported_never_sends(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        self.response = ProviderHttpResult(transport='timeout')
        await self.executor.execute(int(receipt['data']['id']))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_test_response')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertEqual(await db.scalar(text('SELECT completeness FROM hf_usage_record')), 'unknown')
            self.assertIsNone(await db.scalar(text('SELECT output_tokens FROM hf_usage_record')))
        unsupported, _ = await self.request()
        await self.executor.execute(int(unsupported['data']['id']))
        self.assertEqual(self.calls, 1)
        async with self.sessions() as db:
            result = await db.scalar(text('SELECT result FROM hf_credential_test WHERE test_id=:id'), {'id': int(unsupported['data']['id'])})
            self.assertEqual(result['issue'], 'PROBE_UNSUPPORTED')

    async def test_cancel_after_intent_never_repeats_submit(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        identity = int(receipt['data']['id'])
        self.cancel = True
        with self.assertRaises(asyncio.CancelledError):
            await self.executor.execute(identity)
        self.cancel = False
        self.assertFalse(await self.executor.execute(identity))
        self.assertEqual(self.calls, 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_test')), '0')

    async def test_disabled_cost_center_ends_before_transport(self):
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_cost_center SET active='N'"))
            await db.commit()
        self.assertTrue(await self.executor.execute(int(receipt['data']['id'])))
        self.assertEqual(self.calls, 0)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
            self.assertEqual((await db.scalar(text('SELECT result FROM hf_credential_test')))['issue'], 'COST_CENTER_UNAVAILABLE')

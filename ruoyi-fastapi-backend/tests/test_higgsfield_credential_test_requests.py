"""测试受理只登记待执行事实，精确绑定配置且不读取密钥。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import ServiceWarning, PermissionException
from tests import test_higgsfield_credentials as credentials
from module_higgsfield.entity.vo.credential_test_vo import CredentialTestCreate
from module_higgsfield.service.credential_test_service import CredentialTestService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestRequestTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = credentials.CredentialTests.cleanup_schema
    payload = credentials.CredentialTests.payload
    save = credentials.CredentialTests.save

    async def asyncSetUp(self):
        await credentials.CredentialTests.asyncSetUp(self)
        self.owner.user.admin = True
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_user ADD COLUMN dept_id bigint'))
            for name in ('20261027_35_provider_calls.py', '20261027_38_usage_records.py', '20261027_39_billing_facts.py', '20261028_56_cost_centers.py', '20261028_57_credential_tests.py', '20261028_58_credential_test_permission.py'):
                spec = importlib.util.spec_from_file_location('test_request_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
        result, _ = await self.save()
        self.key_id = int(result['data']['versionsSummary'][0]['id'])

    async def request(self, key=None, **changes):
        async with self.sessions() as db:
            return await CredentialTestService.create(db, self.owner, self.key_id,
                CredentialTestCreate(**({'costCenterId': '1', 'acknowledgePotentialCharge': True} | changes)), key or str(uuid4()))

    async def test_pending_binding_and_idempotency(self):
        key = str(uuid4())
        first, replayed = await self.request(key)
        self.assertFalse(replayed)
        again, replayed = await self.request(key)
        self.assertTrue(replayed)
        self.assertEqual(first, again)
        async with self.sessions() as db:
            result = await CredentialTestService.get(db, self.owner, int(first['data']['id']))
            self.assertEqual(result['state'], 'pending')
            self.assertEqual(result['credentialVersionId'], str(self.key_id))
            self.assertEqual(result['connectionVersionId'], self.version_id)
            self.assertEqual(result['costCenterId'], '1')
            self.assertEqual(len(result['configHash']), 64)
            self.assertIsNone(result['providerCallId'])
            self.assertNotIn(self.secret, str(result))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_test')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='request_test'")), 1)
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.request(key)

    async def test_disabled_center_revoked_credential_and_model_rejected(self):
        with self.assertRaises(ServiceWarning):
            await self.request(modelVersionId='999999')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_cost_center SET active='N'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.request()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_cost_center SET active='Y'"))
            await db.execute(text("UPDATE hf_credential_version SET state='4',revoked_time=clock_timestamp()"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.request()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_test')), 0)


    async def test_send_binding_rechecks_current_state_and_snapshot(self):
        from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
        receipt, _ = await self.request()
        async with self.sessions() as db:
            row = await CredentialTestService.get(db, self.owner, int(receipt['data']['id']))
            binding = await CredentialTestBindingService.require(db, self.key_id, 1,
                expected_hash=row['configHash'])
            self.assertEqual(binding.config_hash, row['configHash'])
            self.assertNotIn(self.secret, repr(binding))
            await db.rollback()
        # 账号配置变化后不能沿用旧测试摘要。
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_account SET upstream_project='changed'"))
            await db.commit()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await CredentialTestBindingService.require(db, self.key_id, 1, expected_hash=row['configHash'])
            await db.rollback()
        # 未携带摘要时也必须检查成本中心及凭据的实时状态。
        for change in ("UPDATE hf_cost_center SET active='N'",
                       "UPDATE hf_credential_version SET state='4',revoked_time=clock_timestamp()"):
            async with self.sessions() as db:
                await db.execute(text("UPDATE hf_cost_center SET active='Y'"))
                await db.execute(text(change))
                await db.commit()
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning):
                    await CredentialTestBindingService.require(db, self.key_id, 1)
                await db.rollback()


    async def test_concurrent_intent_claim_is_once_and_committed_before_return(self):
        import asyncio
        from module_higgsfield.service.credential_test_intent_service import CredentialTestIntentService
        receipt, _ = await self.request()
        identity = int(receipt['data']['id'])
        compiled = []
        def compile_probe(binding):
            compiled.append(binding.config_hash)
            return {'model': 'test-only', 'messages': [{'role': 'user', 'content': 'fixture'}]}
        async def claim():
            async with self.sessions() as db:
                return await CredentialTestIntentService.begin(db, identity, compile_probe)
        results = await asyncio.gather(claim(), claim())
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(len(compiled), 1)
        self.assertIsNone(await claim())
        async with self.sessions() as db:
            call = (await db.execute(text('SELECT * FROM hf_provider_call'))).mappings().one()
            self.assertEqual(call['state'], '1')
            self.assertEqual(call['acceptance'], 'unknown')
            self.assertEqual(call['operation'], 'test')
            self.assertEqual(call['cost_center_id'], 1)
            self.assertIsNone(call['job_id'])
            self.assertEqual(await db.scalar(text('SELECT provider_call_id FROM hf_credential_test')), call['call_id'])
            self.assertNotIn('fixture', str(call['request_metadata']))

    async def test_compilation_failure_rolls_back_intent(self):
        from module_higgsfield.service.credential_test_intent_service import CredentialTestIntentService
        receipt, _ = await self.request()
        async with self.sessions() as db:
            with self.assertRaises(ValueError):
                await CredentialTestIntentService.begin(db, int(receipt['data']['id']), lambda binding: {})
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
            self.assertIsNone(await db.scalar(text('SELECT provider_call_id FROM hf_credential_test')))


class CredentialTestInputTests(unittest.TestCase):
    def test_explicit_charge_confirmation(self):
        from pydantic import ValidationError
        for value in (False, 1, 'true', None):
            with self.assertRaises(ValidationError):
                CredentialTestCreate(costCenterId='1', acknowledgePotentialCharge=value)

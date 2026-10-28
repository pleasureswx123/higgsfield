"""使用实际测试执行证据验证启用、配置过期、幂等和撤权。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from tests import test_higgsfield_credential_test_executor as executors
from module_higgsfield.entity.vo.credential_vo import CredentialActivate
from module_higgsfield.service.credential_activation_service import CredentialActivationService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialActivationTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def asyncSetUp(self):
        await executors.CredentialTestExecutorTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location('activation_permission', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_60_credential_activation_permission.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade()
                    module.upgrade()
            await conn.run_sync(migrate)
        receipt, _ = await self.request(modelVersionId=str(self.model_version_id))
        self.test_id = int(receipt['data']['id'])
        await self.executor.execute(self.test_id)
        async with self.sessions() as db:
            self.config_hash = await db.scalar(text('SELECT config_hash FROM hf_credential_test'))

    async def activate(self, key=None, **changes):
        payload = CredentialActivate(**(dict(revision='1', testId=str(self.test_id),
            expectedConfigHash=self.config_hash, reason='核对测试后启用') | changes))
        async with self.sessions() as db:
            return await CredentialActivationService.activate(db, self.owner, self.key_id, payload, key or str(uuid4()))

    async def test_activate_replay_and_recheck_authorization(self):
        for change in ({'revision': '999'}, {'expectedConfigHash': 'a'*64}, {'testId': '999999'}):
            with self.assertRaises(ServiceWarning):
                await self.activate(**change)
        key = str(uuid4())
        first, replayed = await self.activate(key)
        self.assertFalse(replayed)
        self.assertEqual(first['data']['state'], 'active')
        again, replayed = await self.activate(key)
        self.assertTrue(replayed)
        self.assertEqual(first, again)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_version')), '1')
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_provider_credential')), '1')
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='activate'")), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM sys_menu WHERE perms='credential:activate'")), 1)
        self.assertNotIn(self.secret, str(first))
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.activate(key)

    async def test_changed_account_configuration_invalidates_success(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_account SET upstream_project='changed-after-test'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.activate()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_version')), '0')

    async def test_inconsistent_call_evidence_cannot_activate(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_call SET acceptance='unknown'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.activate()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_version')), '0')

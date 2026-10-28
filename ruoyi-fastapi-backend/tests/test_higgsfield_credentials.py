"""凭据保存、隔离、幂等和审计的真实迁移隔离数据库测试。"""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.entity.vo.credential_vo import (
    CredentialCreate,
    CredentialVersionCreate,
    CredentialPage,
    CredentialQuery,
)
from module_higgsfield.entity.vo.provider_vo import ProviderAccountCreate
from module_higgsfield.service.credential_service import CredentialService
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService, CredentialKeyring
from module_higgsfield.service.provider_service import ProviderService
from tests import test_higgsfield_providers as providers


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = providers.ProviderTests.cleanup_schema

    async def asyncSetUp(self):
        await providers.ProviderTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_menu ADD COLUMN component text, ADD COLUMN icon text'))
        for filename in (
            '20261027_05_member_console.py',
            '20261027_15_provider_accounts.py',
            '20261027_16_audit.py',
            '20261027_17_credentials.py',
            '20261027_18_credential_permissions.py',
            '20261027_19_credential_console.py',
            '20261027_20_provider_console.py',
            '20261027_29_jobs_outbox.py',
            '20261027_30_credential_inflight.py',
            '20261027_31_credential_state_permissions.py',
        ):
            spec = importlib.util.spec_from_file_location(
                'credential_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / filename
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            async with self.engine.begin() as conn:

                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration.upgrade()

                await conn.run_sync(migrate)
        async with self.sessions() as db:
            connection, _ = await ProviderService.save(db, self.owner, providers.payload(), str(uuid4()))
            self.version_id = connection['data']['currentVersion']['id']
            account, _ = await ProviderService.create_account(
                db,
                self.owner,
                ProviderAccountCreate(
                    connectionId=connection['data']['id'], accountCode='test', region='eva', upstreamProject='demo'
                ),
                str(uuid4()),
            )
            self.account_id = account['data']['id']
        self.crypto = CredentialCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32))
        self.secret = 'supplier-test-secret-5678'

    def payload(self, **changes):
        return CredentialCreate(
            **dict(
                accountId=self.account_id,
                ownerId='1',
                name='测试凭据',
                connectionVersionId=self.version_id,
                apiKey=self.secret,
                validFrom='2026-01-01T00:00:00Z',
                validUntil='2099-01-01T00:00:00Z',
            )
            | changes
        )

    async def save(self, payload=None, key=None, credential_id=None, user=None):
        async with self.sessions() as db:
            return await CredentialService.save(
                db,
                user or self.owner,
                payload or self.payload(),
                key or str(uuid4()),
                credential_id,
                crypto=self.crypto,
            )

    async def test_inflight_counts_are_version_scoped_and_keep_unknown(self):
        result, _ = await self.save()
        identity = int(result['data']['id'])
        first = result['data']['versionsSummary'][0]['id']
        rotated, _ = await self.save(
            CredentialVersionCreate(
                revision='1',
                connectionVersionId=self.version_id,
                apiKey=self.secret + '2',
                validFrom='2026-01-01T00:00:00Z',
                validUntil='2099-01-01T00:00:00Z',
            ),
            credential_id=identity,
        )
        second = rotated['data']['id']
        async with self.sessions() as db:
            for index, (state, upstream) in enumerate(
                [('0', '0'), ('4', '2'), ('6', '6'), ('5', '6'), ('5', '3'), ('5', '4'), ('5', '5')]
            ):
                db.add(
                    HfCreationJob(
                        project_id=1,
                        actor_id=1,
                        department_snapshot={},
                        kind='image',
                        idempotency_key=f'count:{index}',
                        request_hash='a' * 64,
                        model_version_id=1,
                        model_variant_id=1,
                        credential_version_id=int(first),
                        platform_price_version_id=1,
                        input_snapshot={},
                        orchestration_state=state,
                        upstream_state=upstream,
                        **WriteService.audit(self.owner),
                    )
                )
            db.add(
                HfCreationJob(
                    project_id=1,
                    actor_id=1,
                    department_snapshot={},
                    kind='image',
                    idempotency_key='other-version',
                    request_hash='b' * 64,
                    model_version_id=1,
                    model_variant_id=1,
                    credential_version_id=int(second),
                    platform_price_version_id=1,
                    input_snapshot={},
                    **WriteService.audit(self.owner),
                )
            )
            await db.commit()
            detail = await CredentialService.get(db, self.owner, identity)
            counts = {row['id']: row['inFlightCount'] for row in detail['versionsSummary']}
            self.assertEqual(counts, {first: '4', second: '1'})
            page = await CredentialService.listing(db, self.owner, CredentialPage(pageSize=1), identity)
            self.assertEqual(page.rows[0]['id'], second)
            self.assertEqual(page.rows[0]['inFlightCount'], '1')
            self.assertNotIn('ciphertext', page.rows[0])

    async def test_encrypted_replay_rotation_and_safe_reads(self):
        key = str(uuid4())
        first, _ = await self.save(key=key)
        again, replay = await self.save(key=key)
        self.assertTrue(replay)
        self.assertEqual(first, again)
        identity = int(first['data']['id'])
        with self.assertRaises(ServiceWarning):
            await self.save(self.payload(apiKey='different-test-secret-5678'), key=key)
        rotate = CredentialVersionCreate(
            revision='1',
            connectionVersionId=self.version_id,
            apiKey='rotated-test-secret-9999',
            validFrom='2026-01-01T00:00:00Z',
        )
        rotated, _ = await self.save(rotate, credential_id=identity)
        self.assertEqual(rotated['data']['versionNo'], 2)
        self.assertEqual(rotated['data']['state'], 'draft')
        with self.assertRaises(ServiceWarning):
            await self.save(rotate, credential_id=identity)
        async with self.sessions() as db:
            rows = (await db.scalars(select(HfCredentialVersion).order_by(HfCredentialVersion.version_no))).all()
            self.assertEqual(len(rows), 2)
            self.assertEqual(self.crypto.decrypt(rows[0], identity, int(self.version_id), 1), self.secret.encode())
            self.assertEqual(rows[0].state, '0')
            safe = await CredentialService.listing(db, self.owner, CredentialPage(pageSize=1), identity)
            self.assertEqual(safe.total, 2)
            self.assertTrue(safe.has_next)
            serialized = safe.model_dump_json(by_alias=True)
            for field in ('secretCiphertext', 'nonce', 'authTag', 'masterKeyVersion', 'fingerprint', self.secret):
                self.assertNotIn(field, serialized)
            records = (await db.execute(text('SELECT safe_result FROM hf_api_idempotency_record'))).scalars().all()
            self.assertNotIn(self.secret, json.dumps(records))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 2)
            listed = await CredentialService.listing(db, self.owner, CredentialQuery(accountId=self.account_id))
            self.assertEqual(listed.total, 1)
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM sys_menu m JOIN sys_menu p ON p.menu_id=m.parent_id WHERE m.component='studio/credentials/index' AND p.path='studio' AND m.perms='credential:read'"
                    )
                ),
                1,
            )

    async def test_scope_owner_permission_and_rollback(self):
        denied = SimpleNamespace(user=self.owner.user, permissions=['provider:write'])
        with self.assertRaises(PermissionException):
            await self.save(user=denied)
        for change in ({'ownerId': '99999'}, {'connectionVersionId': '99999'}, {'validUntil': '2026-01-02T00:00:00Z'}):
            with self.assertRaises(ServiceWarning):
                await self.save(self.payload(**change))
        original = ProviderDao.add

        async def fail_audit(db, model, **values):
            if model is HfAuditLog:
                raise RuntimeError(self.secret)
            return await original(db, model, **values)

        with patch.object(ProviderDao, 'add', side_effect=fail_audit):
            with self.assertRaises(ServiceWarning) as error:
                await self.save()
            self.assertNotIn(self.secret, error.exception.message)
            self.assertTrue(error.exception.__suppress_context__)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_credential')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_version')), 0)
        await self.save()

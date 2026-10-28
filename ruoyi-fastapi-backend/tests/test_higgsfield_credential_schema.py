"""隔离数据库中的凭据表约束；不连接供应商、不保存真实密钥。"""

import importlib.util
import os
import unittest
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.credential_do import HfProviderCredential, HfCredentialVersion
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService, CredentialKeyring
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialSchemaTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'credential_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_17_credentials.py',
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)

    async def test_encryption_lengths_unique_nonce_and_comments(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            credential = HfProviderCredential(
                account_id=1,
                credential_name='测试专用',
                owner_id=self.owner.user.user_id,
                status='0',
                revision=1,
                **audit,
            )
            db.add(credential)
            await db.flush()
            credential_id = credential.credential_id
            await db.commit()
        crypto = CredentialCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32))
        encrypted = crypto.encrypt('not-a-real-api-key', credential_id, 1, 1)
        values = {
            name: getattr(encrypted, name)
            for name in ('secret_ciphertext', 'nonce', 'auth_tag', 'master_key_version', 'fingerprint', 'masked_suffix')
        }
        async with self.sessions() as db:
            db.add(
                HfCredentialVersion(
                    credential_id=credential_id,
                    connection_version_id=1,
                    version_no=1,
                    valid_from=TimezoneUtil.utc_now(),
                    state='0',
                    revision=1,
                    **values,
                    **audit,
                )
            )
            await db.commit()
        for changes in ({'nonce': b'short'}, {'auth_tag': b'short'}, {}):
            async with self.sessions() as db:
                with self.assertRaises(IntegrityError):
                    db.add(
                        HfCredentialVersion(
                            credential_id=credential_id,
                            connection_version_id=1,
                            version_no=2,
                            valid_from=TimezoneUtil.utc_now(),
                            state='0',
                            revision=1,
                            **{**values, **changes},
                            **audit,
                        )
                    )
                    await db.flush()
                await db.rollback()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_credential_version')), 1)
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid IN ('hf_provider_credential'::regclass,'hf_credential_version'::regclass) AND contype='f'"
                    )
                ),
                0,
            )
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_attribute WHERE attrelid IN ('hf_provider_credential'::regclass,'hf_credential_version'::regclass) AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                    )
                ),
                0,
            )

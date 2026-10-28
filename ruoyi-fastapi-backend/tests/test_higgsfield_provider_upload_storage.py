"""临时上传迁移约束、复用边界与认证加密身份验证。"""

import importlib.util
import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.provider_upload_dao import ProviderUploadDao
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.provider_upload_crypto_service import ProviderUploadCryptoService
from tests import test_higgsfield_job_storage as storage

MIGRATION_PATH = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_36_provider_uploads.py'


class UploadCryptoTests(unittest.TestCase):
    def test_upload_identity_credential_and_domain_are_authenticated(self) -> None:
        keys = CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32)
        service = ProviderUploadCryptoService(keys)
        encrypted = service.encrypt('https://example.com/file?secret=token', 1, 2)
        self.assertNotIn(b'secret', encrypted)
        self.assertEqual(service.decrypt(encrypted, 1, 2), 'https://example.com/file?secret=token')
        for identity, credential in ((2, 2), (1, 3)):
            with self.assertRaises(ServiceWarning):
                service.decrypt(encrypted, identity, credential)
        with self.assertRaises(ServiceWarning):
            OutputSourceCryptoService(keys).decrypt(encrypted, 1, 2)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderUploadStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self) -> None:
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'provider_upload_storage',
            MIGRATION_PATH,
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.now = datetime.now(UTC).replace(microsecond=0)

    def values(self, **changes: object) -> dict:
        return (
            {
                'asset_version_id': 1,
                'account_id': 2,
                'credential_version_id': 3,
                'provider_call_id': 4,
                'create_time': self.now,
                'update_time': self.now,
                'create_by': 'test',
                'update_by': 'test',
            }
            | changes
        )

    async def test_scope_expiry_and_duplicate_call_constraints(self) -> None:
        until = self.now + timedelta(hours=1)
        async with self.sessions() as db:
            row = await ProviderUploadDao.add(
                db, self.values(state='1', url_ciphertext=b'envelope', expires_time=until)
            )
            self.assertEqual(
                (await ProviderUploadDao.reusable(db, 1, 2, 3, self.now)).provider_upload_id, row.provider_upload_id
            )
            for scope in ((2, 2, 3, self.now), (1, 3, 3, self.now), (1, 2, 4, self.now), (1, 2, 3, until)):
                self.assertIsNone(await ProviderUploadDao.reusable(db, *scope))
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    await ProviderUploadDao.add(db, self.values())
            # 不将素材和账号唯一化，允许新调用产生新的上传历史。
            await ProviderUploadDao.add(db, self.values(provider_call_id=5))
            await db.commit()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_upload')), 2)

    async def test_invalid_ready_source_and_complete_comments(self) -> None:
        async with self.sessions() as db:
            for changes in (
                {'state': '1'},
                {'state': '3', 'url_ciphertext': b'bad'},
                {'state': '9'},
                {'state': '1', 'url_ciphertext': b'bad', 'expires_time': self.now},
            ):
                with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        await ProviderUploadDao.add(db, self.values(**changes))
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute WHERE attrelid='hf_provider_upload'::regclass AND attnum>0 "
                    'AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL'
                )
            )
            self.assertEqual(missing, 0)
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid='hf_provider_upload'::regclass AND contype='f'"
                    )
                ),
                0,
            )

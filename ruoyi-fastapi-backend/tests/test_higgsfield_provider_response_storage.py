"""响应证据迁移、唯一约束与绑定身份认证。"""

import importlib.util
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_higgsfield.entity.do.provider_response_do import HfProviderResponse
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from tests import test_higgsfield_job_storage as storage


class ResponseCryptoTests(unittest.TestCase):
    def test_binary_body_and_context_are_authenticated(self):
        crypto = ProviderResponseCryptoService(CredentialKeyring('v1', {'v1': b'a' * 32}, b'b' * 32))
        raw = b'{"images":["private-response"]}' * 100
        encrypted = crypto.encrypt(raw, 11, 22)
        self.assertNotIn(b'private-response', encrypted)
        self.assertLess(len(encrypted), len(raw) + 256)
        self.assertEqual(crypto.decrypt(encrypted, 11, 22), raw)
        for body, call, job in (
            (encrypted, 12, 22),
            (encrypted, 11, 23),
            (encrypted[:-1], 11, 22),
            (encrypted.replace(b'"format":1', b'"format":2'), 11, 22),
        ):
            with self.assertRaises(ValueError):
                crypto.decrypt(body, call, job)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ResponseStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'responses', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_37_provider_responses.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_call_unique_path_constraints_and_chinese_comments(self):
        now = datetime.now(UTC)
        values = dict(
            provider_call_id=1,
            job_id=2,
            storage_key='provider-evidence/' + 'a' * 32,
            sha256='b' * 64,
            byte_size=100,
            http_status=200,
            create_time=now,
            update_time=now,
        )
        async with self.sessions() as db:
            db.add(HfProviderResponse(**values))
            await db.flush()
            for changes in (
                {'storage_key': 'provider-evidence/' + 'c' * 32},
                {'provider_call_id': 3, 'storage_key': '../outside'},
                {'provider_call_id': 3, 'storage_key': 'provider-evidence/' + 'c' * 32, 'http_status': 0},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfProviderResponse(**(values | changes)))
                        await db.flush()
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid='hf_provider_response'::regclass AND contype='f'"
                    )
                ),
                0,
            )
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute WHERE attrelid='hf_provider_response'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            await db.commit()

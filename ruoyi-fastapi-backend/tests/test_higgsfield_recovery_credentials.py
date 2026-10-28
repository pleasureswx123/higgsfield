"""恢复凭据验证使用测试密钥；不接触真实供应商秘密。"""

import os
import unittest
from dataclasses import asdict
from sqlalchemy import text
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService, CredentialKeyring
from module_higgsfield.service.recovery_credential_service import RecoveryCredentialService
from tests import test_higgsfield_credentials as credentials


class RecoveryCredentialCryptoTests(unittest.TestCase):
    def test_master_key_fingerprint_and_context_failures_are_distinguished(self):
        crypto = CredentialCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32))
        row = asdict(crypto.encrypt('restore-test-secret', 1, 2, 1)) | {
            'credential_id': 1, 'connection_version_id': 2, 'version_no': 1,
        }
        self.assertEqual(RecoveryCredentialService.check(crypto, row), 'verified')
        missing = CredentialCryptoService(CredentialKeyring('new', {'new': b'c' * 32}, b'b' * 32))
        self.assertEqual(RecoveryCredentialService.check(missing, row), 'master_key_missing')
        wrong = CredentialCryptoService(CredentialKeyring('test', {'test': b'c' * 32}, b'b' * 32))
        self.assertEqual(RecoveryCredentialService.check(wrong, row), 'credential_integrity_failed')
        wrong_fingerprint = CredentialCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'c' * 32))
        self.assertEqual(RecoveryCredentialService.check(wrong_fingerprint, row), 'fingerprint_mismatch')
        self.assertEqual(RecoveryCredentialService.check(crypto, row | {'connection_version_id': 3}),
                         'credential_integrity_failed')


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoveryCredentialDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = credentials.CredentialTests.cleanup_schema
    asyncSetUp = credentials.CredentialTests.asyncSetUp
    payload = credentials.CredentialTests.payload
    save = credentials.CredentialTests.save

    async def test_historical_versions_and_reports_do_not_expose_or_rewrite_secrets(self):
        saved, _ = await self.save()
        identity = saved['data']['versionsSummary'][0]['id']
        report = await RecoveryCredentialService.audit(self.sessions, self.crypto, page_size=1)
        self.assertEqual(report['counts'], {'verified': 1})
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_credential_version SET state='4',auth_tag=:tag"), {'tag': b'z' * 16})
            await db.commit()
        report = await RecoveryCredentialService.audit(self.sessions, self.crypto, page_size=1)
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['failures'], [{'credentialVersionId': identity, 'reason': 'credential_integrity_failed'}])
        limited = await RecoveryCredentialService.audit(self.sessions, self.crypto, sample_limit=0)
        self.assertEqual(limited['failed'], 1)
        self.assertEqual(limited['failures'], [])
        self.assertTrue(limited['failuresTruncated'])
        for value in (self.secret, self.secret[-4:], 'auth_tag', 'ciphertext', 'master_key_version'):
            self.assertNotIn(value, str(report))
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT state,auth_tag FROM hf_credential_version'))).one()
            self.assertEqual(row.state, '4')
            self.assertEqual(row.auth_tag, b'z' * 16)

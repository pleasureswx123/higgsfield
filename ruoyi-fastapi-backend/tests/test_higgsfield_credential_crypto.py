"""仅使用测试密钥，验证加密上下文、轮换和失败关闭行为。"""

import base64
import json
import unittest
from dataclasses import replace
from unittest.mock import patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService, CredentialKeyring


class CredentialCryptoTests(unittest.TestCase):
    def setUp(self):
        self.keys = {'test-v1': b'a' * 32, 'test-v2': b'b' * 32}
        self.service = CredentialCryptoService(CredentialKeyring('test-v1', self.keys, b'c' * 32))
        self.secret = 'test-only-supplier-key-1234'

    def test_roundtrip_nonce_and_mask(self):
        first = self.service.encrypt(self.secret, 1, 2, 3)
        second = self.service.encrypt(self.secret, 1, 2, 3)
        self.assertEqual(self.service.decrypt(first, 1, 2, 3), self.secret.encode())
        self.assertNotEqual(first.nonce, second.nonce)
        self.assertNotEqual(first.secret_ciphertext, second.secret_ciphertext)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.masked_suffix, '****1234')
        self.assertEqual(len(first.auth_tag), 16)
        self.assertNotIn(self.secret, repr(first))
        self.assertNotIn(self.secret.encode(), first.secret_ciphertext)

    def test_tampering_and_identity_substitution_fail(self):
        value = self.service.encrypt(self.secret, 1, 2, 3)
        for context in ((2, 2, 3), (1, 3, 3), (1, 2, 4)):
            with self.assertRaises(ServiceWarning):
                self.service.decrypt(value, *context)
        for changed in (
            replace(value, auth_tag=b'x' * 16),
            replace(value, nonce=b'bad'),
            replace(value, secret_ciphertext=b'x' + value.secret_ciphertext[1:]),
        ):
            with self.assertRaises(ServiceWarning):
                self.service.decrypt(changed, 1, 2, 3)

    def test_rotation_preserves_old_decryption_and_stable_fingerprint(self):
        old = self.service.encrypt(self.secret, 1, 2, 3)
        rotated = CredentialCryptoService(CredentialKeyring('test-v2', self.keys, b'c' * 32))
        new = rotated.encrypt(self.secret, 1, 2, 4)
        self.assertEqual(rotated.decrypt(old, 1, 2, 3), self.secret.encode())
        self.assertEqual(old.fingerprint, new.fingerprint)
        self.assertEqual(new.master_key_version, 'test-v2')
        incomplete = CredentialCryptoService(CredentialKeyring('test-v2', {'test-v2': b'b' * 32}, b'c' * 32))
        with self.assertRaises(ServiceWarning):
            incomplete.decrypt(old, 1, 2, 3)

    def test_environment_configuration_fails_closed(self):
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ServiceWarning):
            CredentialKeyring.from_environment()
        env = {
            'HF_CREDENTIAL_MASTER_KEYS': json.dumps({'v1': base64.b64encode(b'a' * 32).decode()}),
            'HF_CREDENTIAL_ACTIVE_KEY_VERSION': 'v1',
            'HF_CREDENTIAL_FINGERPRINT_KEY': base64.b64encode(b'c' * 32).decode(),
        }
        with patch.dict('os.environ', env, clear=True):
            self.assertEqual(CredentialKeyring.from_environment().active_version, 'v1')
        env['HF_CREDENTIAL_MASTER_KEYS'] = 'not-json-secret'
        with patch.dict('os.environ', env, clear=True), self.assertRaises(ServiceWarning):
            CredentialKeyring.from_environment()

    def test_invalid_secret_and_key_lengths(self):
        for secret in ('short', 'test secret', 'test\nsecret', '非ASCII密钥'):
            with self.assertRaises(ServiceWarning):
                self.service.encrypt(secret, 1, 2, 3)
        with self.assertRaises(ValueError):
            CredentialKeyring('v1', {'v1': b'short'}, b'c' * 32)

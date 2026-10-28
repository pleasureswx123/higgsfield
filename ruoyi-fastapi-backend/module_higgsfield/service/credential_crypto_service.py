"""供应商凭据的认证加密；主密钥由运行时注入，不写入数据库。"""

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from module_higgsfield.service.project_workspace_service import WorkspaceService


@dataclass(frozen=True, repr=False)
class CredentialKeyring:
    active_version: str
    keys: dict[str, bytes] = field(repr=False)
    fingerprint_key: bytes = field(repr=False)

    def __post_init__(self):
        if (
            not self.keys
            or self.active_version not in self.keys
            or not isinstance(self.fingerprint_key, bytes)
            or len(self.fingerprint_key) != 32
        ):
            raise ValueError('凭据密钥配置不完整')
        if any(
            not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', version) or not isinstance(key, bytes) or len(key) != 32
            for version, key in self.keys.items()
        ):
            raise ValueError('主密钥版本或长度无效')
        object.__setattr__(self, 'keys', MappingProxyType(dict(self.keys)))

    @classmethod
    def from_environment(cls):
        try:
            raw = json.loads(os.environ['HF_CREDENTIAL_MASTER_KEYS'])
            if not isinstance(raw, dict):
                raise ValueError('密钥环必须为对象')
            keys = {version: base64.b64decode(value, validate=True) for version, value in raw.items()}
            return cls(
                os.environ['HF_CREDENTIAL_ACTIVE_KEY_VERSION'],
                keys,
                base64.b64decode(os.environ['HF_CREDENTIAL_FINGERPRINT_KEY'], validate=True),
            )
        except (KeyError, ValueError, TypeError):
            WorkspaceService.conflict('CREDENTIAL_CRYPTO_UNAVAILABLE', '凭据加密配置不可用，请联系管理员')


@dataclass(frozen=True, repr=False)
class EncryptedCredential:
    secret_ciphertext: bytes
    nonce: bytes
    auth_tag: bytes
    master_key_version: str
    fingerprint: str
    masked_suffix: str


class CredentialCryptoService:
    """AES-256-GCM；密文绑定凭据身份、配置版本和凭据版本号。"""

    def __init__(self, keyring=None):
        self.keyring = keyring or CredentialKeyring.from_environment()

    @staticmethod
    def context(credential_id, connection_version_id, version_no):
        values = (credential_id, connection_version_id, version_no)
        if any(type(value) is not int or not 1 <= value <= 9223372036854775807 for value in values):
            raise ValueError('加密上下文必须使用有效整数业务身份')
        return f'hf:credential:v1:{credential_id}:{connection_version_id}:{version_no}'.encode('ascii')

    def fingerprint(self, secret):
        if (
            not isinstance(secret, str)
            or not 8 <= len(secret) <= 4096
            or any(ord(char) < 33 or ord(char) > 126 for char in secret)
        ):
            WorkspaceService.conflict(
                'CREDENTIAL_SECRET_INVALID', '供应商密钥必须为8至4096个可打印ASCII字符，且不能包含空白'
            )
        return hmac.new(
            self.keyring.fingerprint_key, b'hf:credential:fingerprint:v1:' + secret.encode('ascii'), hashlib.sha256
        ).hexdigest()

    def encrypt(self, secret, credential_id, connection_version_id, version_no):
        fingerprint = self.fingerprint(secret)
        context = self.context(credential_id, connection_version_id, version_no)
        version = self.keyring.active_version
        nonce = os.urandom(12)
        value = secret.encode('ascii')
        encrypted = AESGCM(self.keyring.keys[version]).encrypt(nonce, value, context)
        return EncryptedCredential(encrypted[:-16], nonce, encrypted[-16:], version, fingerprint, '****' + secret[-4:])

    def decrypt(self, encrypted, credential_id, connection_version_id, version_no):
        key = self.keyring.keys.get(encrypted.master_key_version)
        if key is None:
            WorkspaceService.conflict('CREDENTIAL_CRYPTO_UNAVAILABLE', '凭据所需的历史主密钥版本不可用')
        if len(encrypted.nonce) != 12 or len(encrypted.auth_tag) != 16:
            WorkspaceService.conflict('CREDENTIAL_INTEGRITY_FAILED', '凭据认证校验失败')
        try:
            return AESGCM(key).decrypt(
                encrypted.nonce,
                encrypted.secret_ciphertext + encrypted.auth_tag,
                self.context(credential_id, connection_version_id, version_no),
            )
        except InvalidTag:
            WorkspaceService.conflict('CREDENTIAL_INTEGRITY_FAILED', '凭据认证校验失败')

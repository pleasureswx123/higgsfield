"""临时下载地址认证加密，密文绑定任务与输出序号。"""

import base64
import json
import os
from utils.output_source_util import validate_output_source
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.project_workspace_service import WorkspaceService


class OutputSourceCryptoService:
    def __init__(self, keyring=None):
        self.keyring = keyring or CredentialKeyring.from_environment()

    @staticmethod
    def context(job_id, ordinal):
        if (
            type(job_id) is not int
            or not 1 <= job_id <= 9223372036854775807
            or type(ordinal) is not int
            or not 0 <= ordinal <= 2147483647
        ):
            raise ValueError('输出加密上下文无效')
        return f'hf:output-source:v1:{job_id}:{ordinal}'.encode('ascii')

    validate_url = staticmethod(validate_output_source)

    def encrypt(self, value, job_id, ordinal):
        self.validate_url(value)
        version = self.keyring.active_version
        nonce = os.urandom(12)
        encrypted = AESGCM(self.keyring.keys[version]).encrypt(
            nonce, value.encode('utf-8'), self.context(job_id, ordinal)
        )
        return json.dumps(
            {
                'version': version,
                'nonce': base64.b64encode(nonce).decode('ascii'),
                'ciphertext': base64.b64encode(encrypted).decode('ascii'),
            },
            separators=(',', ':'),
        ).encode('ascii')

    def decrypt(self, envelope, job_id, ordinal):
        try:
            record = json.loads(envelope)
            key = self.keyring.keys[record['version']]
            nonce = base64.b64decode(record['nonce'], validate=True)
            ciphertext = base64.b64decode(record['ciphertext'], validate=True)
            if len(nonce) != 12:
                raise ValueError
            result = AESGCM(key).decrypt(nonce, ciphertext, self.context(job_id, ordinal)).decode('utf-8')
            self.validate_url(result)
            return result
        except (KeyError, TypeError, ValueError, InvalidTag, UnicodeError):
            WorkspaceService.conflict('OUTPUT_SOURCE_INTEGRITY_FAILED', '输出源地址无法解密或认证失败')

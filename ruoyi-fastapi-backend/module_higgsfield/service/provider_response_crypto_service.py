"""大响应二进制认证加密，密文绑定原始调用与任务，不使用Base64膨胀正文。"""

import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from module_higgsfield.service.credential_crypto_service import CredentialKeyring

MAX_HEADER_BYTES = 256
NONCE_BYTES = 12
MAX_ID = 9223372036854775807


class ProviderResponseCryptoService:
    def __init__(self, keyring: CredentialKeyring | None = None) -> None:
        self.keyring = keyring or CredentialKeyring.from_environment()

    @staticmethod
    def context(call_id: int, job_id: int) -> bytes:
        if any(type(value) is not int or not 0 < value <= MAX_ID for value in (call_id, job_id)):
            raise ValueError('响应证据绑定身份无效')
        return f'hf:provider-response:v1:{call_id}:{job_id}'.encode()

    def encrypt(self, data: bytes, call_id: int, job_id: int) -> bytes:
        if not isinstance(data, bytes) or not data:
            raise ValueError('响应证据必须为非空字节')
        version = self.keyring.active_version
        header = json.dumps({'format': 1, 'key': version}, separators=(',', ':')).encode()
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self.keyring.keys[version]).encrypt(nonce, data, self.context(call_id, job_id) + header)
        return header + b'\n' + nonce + ciphertext

    def decrypt(self, data: bytes, call_id: int, job_id: int) -> bytes:
        try:
            boundary = data.index(b'\n', 0, MAX_HEADER_BYTES)
            header, body = data[:boundary], data[boundary + 1 :]
            record = json.loads(header)
            if record.get('format') != 1 or set(record) != {'format', 'key'}:
                raise ValueError
            return AESGCM(self.keyring.keys[record['key']]).decrypt(
                body[:NONCE_BYTES],
                body[NONCE_BYTES:],
                self.context(call_id, job_id) + header,
            )
        except Exception:
            raise ValueError('响应证据无法认证解密') from None

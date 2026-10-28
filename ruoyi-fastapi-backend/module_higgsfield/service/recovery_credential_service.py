"""供应商凭据主密钥与指纹密钥恢复核验；明文不进入报告。"""

import hmac
from collections import Counter
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.recovery_credential_dao import RecoveryCredentialDao
from module_higgsfield.service.credential_crypto_service import EncryptedCredential


class RecoveryCredentialService:
    @staticmethod
    def check(crypto, row):
        if row['master_key_version'] not in crypto.keyring.keys:
            return 'master_key_missing'
        secret = None
        try:
            encrypted = EncryptedCredential(**{key: row[key] for key in (
                'secret_ciphertext', 'nonce', 'auth_tag', 'master_key_version', 'fingerprint', 'masked_suffix')})
            secret = crypto.decrypt(encrypted, row['credential_id'], row['connection_version_id'], row['version_no'])
            fingerprint = crypto.fingerprint(secret.decode('ascii'))
            if not hmac.compare_digest(fingerprint, row['fingerprint']):
                return 'fingerprint_mismatch'
            return 'verified'
        except (ServiceWarning, ValueError, TypeError):
            return 'credential_integrity_failed'
        finally:
            # 不保留明文引用；Python不可变字节不承诺可验证的内存擦除。
            secret = None

    @classmethod
    async def audit(cls, sessions, crypto, *, page_size=200, sample_limit=100):
        if not 1 <= page_size <= 500 or not 0 <= sample_limit <= 1000:
            raise ValueError('核验分页或样本数量不合法')
        counts, failures, after_id = Counter(), [], 0
        while True:
            async with sessions() as db:
                await db.execute(text('SET TRANSACTION READ ONLY'))
                rows = await RecoveryCredentialDao.page(db, after_id, page_size)
            if not rows:
                break
            for row in rows:
                result = cls.check(crypto, row)
                counts[result] += 1
                if result != 'verified' and len(failures) < sample_limit:
                    failures.append({'credentialVersionId': str(row['credential_version_id']), 'reason': result})
            after_id = rows[-1]['credential_version_id']
        total = sum(counts.values())
        failed = total - counts['verified']
        return {'scope': 'credential_key_recovery', 'complete': True,
                'total': total, 'failed': failed, 'counts': dict(counts),
                'failures': failures, 'failuresTruncated': failed > len(failures)}

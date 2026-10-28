"""响应证据认证恢复核验；复用业务读取协议，不返回解密正文。"""

from collections import Counter
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.recovery_file_dao import RecoveryFileDao
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
from module_higgsfield.service.provider_http_service import HARD_RESPONSE_BYTES


class RecoveryEvidenceService:
    @staticmethod
    async def audit(sessions, storage, keyring, *, page_size=200, sample_limit=100):
        if not 1 <= page_size <= 500 or not 0 <= sample_limit <= 1000:
            raise ValueError('核验分页或样本数量不合法')
        counts, failures = Counter(), []
        sources = {}
        for source, crypto_type in (
            ('provider_response', ProviderResponseCryptoService),
            ('credential_test_response', CredentialTestResponseCryptoService),
        ):
            reader = ProviderResponseStorageService(storage, crypto_type(keyring), max_bytes=HARD_RESPONSE_BYTES)
            after_id, current = 0, Counter()
            while True:
                async with sessions() as db:
                    await db.execute(text('SET TRANSACTION READ ONLY'))
                    rows = await RecoveryFileDao.page(db, after_id, page_size, source)
                if not rows:
                    break
                for row in rows:
                    try:
                        # load已验证大小、摘要、认证上下文和JSON；返回值立即丢弃。
                        await reader.load(row, row['call_id'], row['context_id'])
                        result = 'verified'
                    except (ValueError, TypeError):
                        result = 'evidence_verification_failed'
                    except (ServiceWarning, OSError):
                        result = 'unreadable'
                    counts[result] += 1
                    current[result] += 1
                    if result != 'verified' and len(failures) < sample_limit:
                        failures.append({'source': source, 'recordId': str(row['file_id']), 'reason': result})
                after_id = rows[-1]['file_id']
            sources[source] = dict(current)
        total = sum(counts.values())
        failed = total - counts['verified']
        return {'scope': 'response_evidence_authentication', 'complete': True,
                'total': total, 'failed': failed, 'counts': dict(counts), 'sources': sources,
                'failures': failures, 'failuresTruncated': failed > len(failures)}

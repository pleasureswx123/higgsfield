"""隔离恢复环境的文件完整性核验，不修改文件状态或媒体内容。"""

import asyncio
import hashlib
import re
from collections import Counter

from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.recovery_file_dao import RecoveryFileDao


class RecoveryFileService:
    @staticmethod
    def check(storage, row):
        if row['state'] == '4':
            return 'purged_skipped'
        if (not isinstance(row['sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', row['sha256'])
                or not isinstance(row['byte_size'], int) or row['byte_size'] < 0):
            return 'invalid_metadata'
        try:
            with storage.open_key(row['storage_key']) as handle:
                digest = hashlib.sha256()
                size = 0
                while chunk := handle.read(1024 * 1024):
                    size += len(chunk)
                    # 已能确认大小不符时停止，避免损坏文件造成无界读取。
                    if size > row['byte_size']:
                        return 'size_mismatch'
                    digest.update(chunk)
                if size != row['byte_size']:
                    return 'size_mismatch'
                if digest.hexdigest() != row['sha256']:
                    return 'hash_mismatch'
        except ValueError:
            return 'invalid_storage_key'
        except (OSError, ServiceWarning):
            # 受控存储不会向调用方区分缺失、断挂和权限错误，不伪造具体原因。
            return 'unreadable'
        return 'verified'

    @classmethod
    async def audit(cls, sessions, storage, *, page_size=200, sample_limit=100):
        if not 1 <= page_size <= 500 or not 0 <= sample_limit <= 1000:
            raise ValueError('核验分页或样本数量不合法')
        await asyncio.to_thread(storage.verify_root)
        counts = Counter()
        failures = []
        source_counts = {}
        for source in RecoveryFileDao.SOURCES:
            after_id = 0
            current_counts = Counter()
            while True:
                async with sessions() as db:
                    await db.execute(text('SET TRANSACTION READ ONLY'))
                    rows = await RecoveryFileDao.page(db, after_id, page_size, source)
                if not rows:
                    break
                # 关闭数据库会话后再执行阻塞存储读取，不持有长事务或任务锁。
                for row in rows:
                    result = await asyncio.to_thread(cls.check, storage, row)
                    counts[result] += 1
                    current_counts[result] += 1
                    if result not in ('verified', 'purged_skipped') and len(failures) < sample_limit:
                        failures.append({'source': source, 'recordId': str(row['file_id']), 'reason': result})
                after_id = rows[-1]['file_id']
            source_counts[source] = dict(current_counts)
        total = sum(counts.values())
        failed = total - counts['verified'] - counts['purged_skipped']
        return {
            'scope': 'persistent_file_integrity', 'complete': True, 'sources': source_counts,
            'total': total, 'failed': failed, 'counts': dict(counts),
            'failures': failures, 'failuresTruncated': failed > len(failures),
            'fullRecoveryVerified': False,
        }

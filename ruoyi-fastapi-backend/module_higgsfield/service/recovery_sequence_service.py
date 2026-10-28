"""恢复后主键序列的只读冲突检查，不自动调用setval。"""

from sqlalchemy import text
from module_higgsfield.dao.recovery_sequence_dao import RecoverySequenceDao


class RecoverySequenceService:
    @staticmethod
    def reason(row):
        if not row['sequence_name']:
            return 'missing_sequence'
        if row['seqincrement'] != 1 or row['seqcycle']:
            return 'unsupported_sequence_policy'
        candidate = row['last_value'] + (1 if row['is_called'] else 0)
        if candidate > row['seqmax']:
            return 'sequence_exhausted'
        if row['max_id'] is not None and candidate <= row['max_id']:
            return 'sequence_behind'
        return None

    @classmethod
    async def audit(cls, sessions, *, sample_limit=100):
        if not 0 <= sample_limit <= 1000:
            raise ValueError('核验样本数量不合法')
        async with sessions() as db:
            await db.execute(text('SET TRANSACTION READ ONLY'))
            rows = await RecoverySequenceDao.inventory(db)
        failures = []
        failed = 0
        for row in rows:
            reason = cls.reason(row)
            if reason:
                failed += 1
                if len(failures) < sample_limit:
                    failures.append({'table': row['table_name'], 'column': row['column_name'], 'reason': reason})
        return {'scope': 'visible_business_primary_key_sequences', 'complete': True,
                'total': len(rows), 'failed': failed, 'failures': failures,
                'failuresTruncated': failed > len(failures)}

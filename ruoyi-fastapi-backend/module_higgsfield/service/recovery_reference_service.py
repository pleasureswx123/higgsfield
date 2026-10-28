"""历史引用完整性只读核验，不能以删除记录掩盖恢复缺失。"""

from sqlalchemy import text
from module_higgsfield.dao.recovery_reference_dao import RecoveryReferenceDao


class RecoveryReferenceService:
    @staticmethod
    async def audit(sessions, *, sample_limit=100):
        if not 0 <= sample_limit <= 1000:
            raise ValueError('核验样本数量不合法')
        counts, failures = {}, []
        async with sessions() as db:
            await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            for rule in RecoveryReferenceDao.RULES:
                count, ids = await RecoveryReferenceDao.check(db, rule, sample_limit - len(failures))
                counts[rule] = count
                failures.extend({'rule': rule, 'recordId': str(identity)} for identity in ids)
        failed = sum(counts.values())
        return {'scope': 'asset_output_element_references', 'complete': True,
                'rulesChecked': len(counts), 'counts': counts, 'failed': failed,
                'failures': failures, 'failuresTruncated': failed > len(failures)}

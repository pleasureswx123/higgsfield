"""计费对象及用量修订DAO；调用方先锁任务，按对象串行追加。"""

from sqlalchemy import select

from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord


class UsageDao:
    @staticmethod
    async def job_evidence_states(db, job_id):
        return (
            await db.execute(
                select(HfBillingSubject.subject_id, HfUsageRecord.completeness)
                .outerjoin(HfUsageRecord, HfUsageRecord.subject_id == HfBillingSubject.subject_id)
                .where(HfBillingSubject.job_id == job_id, HfBillingSubject.subject_kind == 'generation')
            )
        ).all()

    @staticmethod
    async def subject(db, origin_call_id, subject_kind='generation'):
        return await db.scalar(
            select(HfBillingSubject)
            .where(
                HfBillingSubject.origin_call_id == origin_call_id,
                HfBillingSubject.subject_kind == subject_kind,
            )
            .with_for_update()
        )

    @staticmethod
    async def by_hash(db, subject_id, payload_hash):
        return await db.scalar(
            select(HfUsageRecord).where(
                HfUsageRecord.subject_id == subject_id,
                HfUsageRecord.payload_hash == payload_hash,
            )
        )

    @staticmethod
    async def latest(db, subject_id):
        return await db.scalar(
            select(HfUsageRecord)
            .where(HfUsageRecord.subject_id == subject_id)
            .order_by(HfUsageRecord.revision_no.desc())
            .limit(1)
        )

    @staticmethod
    async def add(db, model, values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

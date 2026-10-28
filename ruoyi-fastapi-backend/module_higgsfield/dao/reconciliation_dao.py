"""对账 DAO；所有账单写入先取账号事务锁，再按批次、明细加锁。"""
from sqlalchemy import select, text, func
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationBatch, HfReconciliationLine, HfReconciliationObservation
from module_higgsfield.entity.do.provider_do import HfProviderAccount
from module_higgsfield.entity.do.asset_do import HfStoredFile, HfUploadSession, HfUploadBinding
from module_higgsfield.entity.do.usage_do import HfBillingSubject


class ReconciliationDao:
    @staticmethod
    async def observation(db, identity):
        return await db.scalar(select(HfReconciliationObservation).where(
            HfReconciliationObservation.observation_id == identity))

    @staticmethod
    async def flush(db):
        await db.flush()

    @staticmethod
    async def line_by_id(db, line_id, lock=False):
        query = select(HfReconciliationLine).where(HfReconciliationLine.line_id == line_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(query)

    @staticmethod
    async def subject(db, subject_id):
        return await db.scalar(select(HfBillingSubject).where(HfBillingSubject.subject_id == subject_id)
            .with_for_update(read=True))

    @staticmethod
    async def batch_line_states(db, batch_id):
        return (await db.scalars(select(HfReconciliationLine.status).join(HfReconciliationObservation,
            HfReconciliationObservation.canonical_line_id == HfReconciliationLine.line_id)
            .where(HfReconciliationObservation.batch_id == batch_id).distinct())).all()

    @staticmethod
    async def page(db, query):
        statement = select(HfReconciliationBatch)
        if query.account_id:
            statement = statement.where(HfReconciliationBatch.account_id == int(query.account_id))
        if query.status:
            state = {'imported': '0', 'matching': '1', 'confirmed': '2', 'disputed': '3'}[query.status]
            statement = statement.where(HfReconciliationBatch.status == state)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await db.scalars(statement.order_by(HfReconciliationBatch.batch_id.desc())
            .offset((query.page_num-1)*query.page_size).limit(query.page_size))).all()
        return rows, total

    @staticmethod
    async def line_page(db, batch_id, query):
        statement = select(HfReconciliationObservation, HfReconciliationLine).join(HfReconciliationLine,
            HfReconciliationLine.line_id == HfReconciliationObservation.canonical_line_id).where(
                HfReconciliationObservation.batch_id == batch_id)
        if query.status:
            state = {'unmatched': '0', 'matched': '1', 'confirmed': '2', 'disputed': '3'}[query.status]
            statement = statement.where(HfReconciliationLine.status == state)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await db.execute(statement.order_by(HfReconciliationObservation.line_no,
            HfReconciliationObservation.observation_id).offset((query.page_num-1)*query.page_size)
            .limit(query.page_size))).all()
        return rows, total

    @staticmethod
    async def batch_counts(db, batch_ids):
        if not batch_ids:
            return {}
        rows = (await db.execute(select(HfReconciliationObservation.batch_id, func.count(),
            func.count().filter(HfReconciliationLine.status.in_(('1', '2'))),
            func.count().filter(HfReconciliationLine.status == '3'))
            .join(HfReconciliationLine, HfReconciliationLine.line_id == HfReconciliationObservation.canonical_line_id)
            .where(HfReconciliationObservation.batch_id.in_(batch_ids))
            .group_by(HfReconciliationObservation.batch_id))).all()
        return {row[0]: {'total': row[1], 'matched': row[2], 'disputed': row[3]} for row in rows}

    @staticmethod
    async def counts(db, batch_id):
        row = (await db.execute(select(func.count(),
            func.count().filter(HfReconciliationLine.status.in_(('1', '2'))),
            func.count().filter(HfReconciliationLine.status == '3'))
            .select_from(HfReconciliationObservation)
            .join(HfReconciliationLine, HfReconciliationLine.line_id == HfReconciliationObservation.canonical_line_id)
            .where(HfReconciliationObservation.batch_id == batch_id))).one()
        return {'total': row[0], 'matched': row[1], 'disputed': row[2]}

    @staticmethod
    async def candidates(db, limit):
        return (await db.scalars(select(HfReconciliationBatch.batch_id).where(
            HfReconciliationBatch.status == '0').order_by(HfReconciliationBatch.update_time,
                HfReconciliationBatch.batch_id).limit(limit))).all()

    @staticmethod
    async def file_context(db, batch_id):
        return (await db.execute(select(HfReconciliationBatch, HfStoredFile, HfUploadSession)
            .join(HfStoredFile, HfStoredFile.file_id == HfReconciliationBatch.source_file_id)
            .join(HfUploadBinding, HfUploadBinding.reconciliation_batch_id == HfReconciliationBatch.batch_id)
            .join(HfUploadSession, HfUploadSession.upload_id == HfUploadBinding.session_id)
            .where(HfReconciliationBatch.batch_id == batch_id))).first()

    @staticmethod
    async def account(db, account_id):
        return await db.scalar(select(HfProviderAccount).where(HfProviderAccount.account_id == account_id))

    @staticmethod
    async def duplicate_file(db, account_id, start, end, digest):
        return await db.scalar(select(HfReconciliationBatch).where(
            HfReconciliationBatch.account_id == account_id, HfReconciliationBatch.period_start == start,
            HfReconciliationBatch.period_end == end, HfReconciliationBatch.file_hash == digest))

    @staticmethod
    async def lock_account(db, account_id):
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {'key': f'hf:reconciliation:account:{account_id}'})

    @staticmethod
    async def batch(db, batch_id, lock=False):
        query = select(HfReconciliationBatch).where(HfReconciliationBatch.batch_id == batch_id)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(query)

    @staticmethod
    async def observations(db, batch_id):
        return (await db.scalars(select(HfReconciliationObservation).where(
            HfReconciliationObservation.batch_id == batch_id).order_by(HfReconciliationObservation.line_no))).all()

    @staticmethod
    async def line(db, account_id, external_line_key):
        return await db.scalar(select(HfReconciliationLine).where(
            HfReconciliationLine.account_id == account_id,
            HfReconciliationLine.external_line_key == external_line_key).with_for_update())

    @staticmethod
    async def affected_batches(db, line_ids):
        if not line_ids:
            return []
        ids = select(HfReconciliationObservation.batch_id).where(
            HfReconciliationObservation.canonical_line_id.in_(line_ids)).distinct()
        return (await db.scalars(select(HfReconciliationBatch).where(
            HfReconciliationBatch.batch_id.in_(ids)).order_by(HfReconciliationBatch.batch_id)
            .with_for_update().execution_options(populate_existing=True))).all()

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

from sqlalchemy import func, select

from module_higgsfield.entity.do.asset_do import HfUploadBinding, HfUploadSession
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.do.price_do import HfPriceSource


class PriceSourceDao:
    @staticmethod
    async def page(db, query):
        statement = select(HfPriceSource)
        if query.q.strip():
            statement = statement.where(HfPriceSource.excerpt.contains(query.q.strip(), autoescape=True))
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await db.scalars(statement.order_by(HfPriceSource.source_id.desc())
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

    @staticmethod
    async def upload(db, source_id):
        return await db.scalar(select(HfUploadSession).join(HfUploadBinding,
            HfUploadBinding.session_id == HfUploadSession.upload_id).where(
                HfUploadBinding.price_source_id == int(source_id)))

    @staticmethod
    async def get(db, source_id):
        return await db.scalar(select(HfPriceSource).where(HfPriceSource.source_id == int(source_id)))

    @staticmethod
    async def add(db, values):
        row = HfPriceSource(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def audit(db, values):
        db.add(HfAuditLog(**values))
        await db.flush()

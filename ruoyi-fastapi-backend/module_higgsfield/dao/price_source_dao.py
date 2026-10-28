from sqlalchemy import select
from module_higgsfield.entity.do.price_do import HfPriceSource
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.do.asset_do import HfUploadBinding, HfUploadSession


class PriceSourceDao:
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

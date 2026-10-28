"""元素导入批次锁与候选持久化；事务由服务管理。"""
from sqlalchemy import select, func
from module_higgsfield.entity.do.element_import_do import HfImportJob, HfImportRow
from module_higgsfield.entity.do.asset_do import HfStoredFile, HfUploadBinding, HfUploadSession


class ElementImportDao:
    @staticmethod
    async def locked_rows(db, identity):
        return (await db.scalars(select(HfImportRow).where(HfImportRow.import_job_id == identity)
            .order_by(HfImportRow.row_no).with_for_update().execution_options(populate_existing=True))).all()

    @staticmethod
    async def candidates(db, limit):
        return (await db.scalars(select(HfImportJob.import_id).where(HfImportJob.status == '0')
            .order_by(HfImportJob.update_time, HfImportJob.import_id).limit(limit))).all()

    @staticmethod
    async def file_context(db, identity):
        return (await db.execute(select(HfImportJob, HfStoredFile, HfUploadSession, HfUploadBinding)
            .join(HfStoredFile, HfStoredFile.file_id == HfImportJob.source_file_id)
            .join(HfUploadBinding, HfUploadBinding.import_job_id == HfImportJob.import_id)
            .join(HfUploadSession, HfUploadSession.upload_id == HfUploadBinding.session_id)
            .where(HfImportJob.import_id == identity))).first()

    @staticmethod
    async def job(db, identity, *, lock=False):
        statement = select(HfImportJob).where(HfImportJob.import_id == identity)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(statement)

    @staticmethod
    async def count_rows(db, identity):
        return await db.scalar(select(func.count()).select_from(HfImportRow).where(HfImportRow.import_job_id == identity))

    @staticmethod
    async def add_rows(db, rows):
        db.add_all([HfImportRow(**values) for values in rows])
        await db.flush()

    @staticmethod
    async def page_rows(db, identity, query):
        conditions = [HfImportRow.import_job_id == identity]
        if query.state is not None:
            conditions.append(HfImportRow.state == {'pending': '0', 'succeeded': '1', 'failed': '2'}[query.state])
        total = await db.scalar(select(func.count()).select_from(HfImportRow).where(*conditions))
        rows = (await db.scalars(select(HfImportRow).where(*conditions).order_by(HfImportRow.row_no)
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

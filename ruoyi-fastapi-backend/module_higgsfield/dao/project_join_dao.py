"""加入申请读取与行锁，事务由服务层管理。"""
from sqlalchemy import select, func
from module_higgsfield.entity.do.project_join_do import HfProjectJoinRequest as Join


class ProjectJoinDao:
    @staticmethod
    async def get(db, identity, lock=False):
        query = select(Join).where(Join.request_id == identity)
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(query)

    @staticmethod
    async def page(db, project_id, query):
        conditions = [Join.project_id == project_id]
        if query.status:
            conditions.append(Join.status == str(('pending', 'approved', 'rejected', 'cancelled').index(query.status)))
        total = await db.scalar(select(func.count()).select_from(Join).where(*conditions))
        rows = (await db.scalars(select(Join).where(*conditions).order_by(Join.create_time.desc(), Join.request_id.desc())
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

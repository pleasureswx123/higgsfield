"""视图偏好数据操作。"""
from sqlalchemy import select
from module_higgsfield.entity.do.view_preference_do import HfUserViewPreference


class ViewPreferenceDao:
    @staticmethod
    async def get(db, user_id, view_key, project_id, lock=False):
        stmt = select(HfUserViewPreference).where(HfUserViewPreference.user_id == user_id,
            HfUserViewPreference.view_key == view_key, HfUserViewPreference.project_id == project_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(stmt)

    @staticmethod
    async def insert(db, **fields):
        row = HfUserViewPreference(**fields)
        db.add(row)
        await db.flush()
        return row

"""个人导航数据访问，所有写操作由服务管理事务。"""
from sqlalchemy import func, select, text, update

from module_higgsfield.entity.do.project_preference_do import HfProjectCollection, HfUserProjectPreference


class PreferenceDao:
    @staticmethod
    async def lock_user(db, user_id):
        # 同一用户的集合删除与移入串行，防止无外键情况下产生悬空关系。
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))'),
                         {'scope': f'hf-personal-project-navigation:{user_id}'})

    @staticmethod
    async def collection(db, user_id, identity, lock=False):
        stmt = select(HfProjectCollection).where(HfProjectCollection.user_id == user_id,
                                                HfProjectCollection.collection_id == identity)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(stmt)

    @staticmethod
    async def collections(db, user_id, query):
        stmt = select(HfProjectCollection).where(HfProjectCollection.user_id == user_id)
        total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await db.scalars(stmt.order_by(HfProjectCollection.order_num, HfProjectCollection.collection_id)
                                .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total

    @staticmethod
    async def name_used(db, user_id, name, except_id=0):
        return await db.scalar(select(HfProjectCollection.collection_id).where(
            HfProjectCollection.user_id == user_id, HfProjectCollection.collection_name == name,
            HfProjectCollection.collection_id != except_id))

    @staticmethod
    async def preference(db, user_id, project_id, lock=False):
        stmt = select(HfUserProjectPreference).where(HfUserProjectPreference.user_id == user_id,
                                                   HfUserProjectPreference.project_id == project_id)
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return await db.scalar(stmt)

    @staticmethod
    async def insert(db, model, **fields):
        row = model(**fields)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def remove_collection(db, row, user_name, now):
        await db.execute(update(HfUserProjectPreference).where(
            HfUserProjectPreference.user_id == row.user_id,
            HfUserProjectPreference.collection_id == row.collection_id).values(
                collection_id=None, revision=HfUserProjectPreference.revision + 1,
                update_by=user_name, update_time=now))
        # 与视图保存共用本人导航锁，原子解除已保存筛选并使旧修订失效。
        await db.execute(text("""UPDATE hf_user_view_preference
            SET settings=jsonb_set(settings, '{collectionId}', 'null'::jsonb),
                revision=revision+1, update_by=:name, update_time=:now
            WHERE user_id=:user_id AND view_key='projects' AND project_id IS NULL
                AND settings->>'collectionId'=:collection_id"""),
            {'name': user_name, 'now': now, 'user_id': row.user_id, 'collection_id': str(row.collection_id)})
        await db.delete(row)
        await db.flush()

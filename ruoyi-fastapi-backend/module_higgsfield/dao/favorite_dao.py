"""收藏关系的原子恢复和本人分页；目标内容授权由Service实时复核。"""
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from module_higgsfield.entity.do.favorite_do import HfFavorite


class FavoriteDao:
    targets = {'element': HfFavorite.element_id, 'asset': HfFavorite.asset_id, 'output': HfFavorite.output_id}

    @staticmethod
    async def owned(db, user_id, identity):
        return await db.scalar(select(HfFavorite).where(HfFavorite.favorite_id == identity, HfFavorite.user_id == user_id))

    @classmethod
    async def save(cls, db, user_id, kind, identity, audit):
        column = cls.targets[kind]
        statement = insert(HfFavorite).values(user_id=user_id, **{column.key: identity}, **audit)
        statement = statement.on_conflict_do_update(index_elements=[HfFavorite.user_id, column],
            index_where=column.is_not(None), set_={'del_flag': '0', 'update_by': audit['update_by'],
                                                 'update_time': audit['update_time']})
        return (await db.execute(statement.returning(HfFavorite),
                                 execution_options={'populate_existing': True})).scalar_one()

    @staticmethod
    async def cancel(db, user_id, identity, audit):
        return (await db.execute(update(HfFavorite).where(HfFavorite.favorite_id == identity,
            HfFavorite.user_id == user_id).values(del_flag='2', update_by=audit['update_by'],
            update_time=audit['update_time']).returning(HfFavorite),
            execution_options={'populate_existing': True})).scalar_one_or_none()

    @classmethod
    async def page(cls, db, user_id, query):
        filters = [HfFavorite.user_id == user_id, HfFavorite.del_flag == '0']
        if query.kind:
            filters.append(cls.targets[query.kind].is_not(None))
        count = await db.scalar(select(func.count()).select_from(HfFavorite).where(*filters))
        rows = (await db.scalars(select(HfFavorite).where(*filters)
            .order_by(HfFavorite.create_time.desc(), HfFavorite.favorite_id.desc())
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, count

from sqlalchemy import select, func
from module_higgsfield.entity.do.model_do import (
    HfProviderConnection,
    HfModelProfile,
    HfModelProfileVersion,
    HfModelVariant,
)


class ModelDao:
    @staticmethod
    async def variants(db, version_id):
        return (
            await db.scalars(
                select(HfModelVariant)
                .where(HfModelVariant.model_version_id == version_id)
                .order_by(HfModelVariant.variant_id)
            )
        ).all()

    @staticmethod
    async def connection(db, connection_id):
        return await db.scalar(
            select(HfProviderConnection).where(HfProviderConnection.connection_id == connection_id).with_for_update()
        )

    @staticmethod
    async def model(db, model_id, lock=False):
        query = select(HfModelProfile).where(HfModelProfile.model_id == model_id)
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def version(db, version_id, lock=False):
        query = (
            select(HfModelProfileVersion)
            .where(HfModelProfileVersion.model_version_id == version_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def code_exists(db, connection_id, code):
        return await db.scalar(
            select(HfModelProfile.model_id).where(
                HfModelProfile.connection_id == connection_id, HfModelProfile.code == code
            )
        )

    @staticmethod
    async def next_version(db, model_id):
        return (
            await db.scalar(
                select(func.max(HfModelProfileVersion.version_no)).where(HfModelProfileVersion.model_id == model_id)
            )
            or 0
        ) + 1

    @staticmethod
    async def variant_exists(db, version_id, key):
        return await db.scalar(
            select(HfModelVariant.variant_id).where(
                HfModelVariant.model_version_id == version_id, HfModelVariant.variant_key == key
            )
        )

    @staticmethod
    async def page(db, kind, parent_id, page_num, page_size, query=None):
        if kind == 'models':
            statement = select(HfModelProfile)
            if query.connection_id:
                statement = statement.where(HfModelProfile.connection_id == int(query.connection_id))
            if query.kind:
                statement = statement.where(HfModelProfile.kind == query.kind)
            order = HfModelProfile.model_id
        elif kind == 'versions':
            statement = select(HfModelProfileVersion).where(HfModelProfileVersion.model_id == parent_id)
            order = HfModelProfileVersion.model_version_id
        else:
            statement = select(HfModelVariant).where(HfModelVariant.model_version_id == parent_id)
            order = HfModelVariant.variant_id
        count = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(statement.order_by(order.desc()).offset((page_num - 1) * page_size).limit(page_size))
        ).all()
        return rows, count

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

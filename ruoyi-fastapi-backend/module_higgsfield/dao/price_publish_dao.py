from sqlalchemy import select, func, or_
from module_higgsfield.entity.do.price_do import HfPriceActivation, HfPricePublishEvent, HfPriceBook


class PricePublishDao:
    @staticmethod
    async def book(db, identity):
        return await db.scalar(select(HfPriceBook).where(HfPriceBook.price_book_id == identity))

    @staticmethod
    async def activation(db, identity, lock=False):
        statement = select(HfPriceActivation).where(HfPriceActivation.activation_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def overlap(db, book_id, start, end, exclude=None):
        statement = select(HfPriceActivation.activation_id).where(
            HfPriceActivation.price_book_id == book_id,
            or_(HfPriceActivation.effective_until.is_(None), HfPriceActivation.effective_until > start),
        )
        if end is not None:
            statement = statement.where(HfPriceActivation.effective_from < end)
        if exclude is not None:
            statement = statement.where(HfPriceActivation.activation_id != exclude)
        return await db.scalar(statement.limit(1))

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def history(db, version_id, query):
        statement = select(HfPricePublishEvent).where(HfPricePublishEvent.price_version_id == int(version_id))
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfPricePublishEvent.publish_event_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

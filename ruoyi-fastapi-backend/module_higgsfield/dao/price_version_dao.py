from decimal import Decimal
from sqlalchemy import select, func, delete
from module_higgsfield.entity.do.price_do import (
    HfPriceBook,
    HfPriceVersion,
    HfPriceRuleItem,
    HfPriceSource,
    HfPriceVersionSource,
)
from module_higgsfield.entity.do.model_do import HfModelVariant


class PriceVersionDao:
    @staticmethod
    async def simulation_scope(db, book_id):
        return (
            await db.execute(
                select(HfPriceBook, HfModelVariant)
                .join(HfModelVariant, HfModelVariant.variant_id == HfPriceBook.model_variant_id)
                .where(HfPriceBook.price_book_id == book_id)
            )
        ).first()

    @staticmethod
    async def book(db, identity):
        return await db.scalar(select(HfPriceBook).where(HfPriceBook.price_book_id == int(identity)).with_for_update())

    @staticmethod
    async def version(db, identity, lock=False):
        statement = select(HfPriceVersion).where(HfPriceVersion.price_version_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def add(db, book_id, user_id, scale, rounding, audit):
        number = await db.scalar(
            select(func.coalesce(func.max(HfPriceVersion.version_no), 0)).where(HfPriceVersion.price_book_id == book_id)
        )
        row = HfPriceVersion(
            price_book_id=book_id,
            version_no=number + 1,
            calculation_scale=scale,
            rounding_mode=rounding,
            create_user_id=user_id,
            **audit,
        )
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def sources_exist(db, ids):
        if not ids:
            return True
        found = (
            await db.scalars(
                select(HfPriceSource.source_id).where(HfPriceSource.source_id.in_([int(value) for value in ids]))
            )
        ).all()
        return len(found) == len(ids)

    @staticmethod
    async def replace(db, version_id, items, sources, audit):
        if items is not None:
            await db.execute(delete(HfPriceRuleItem).where(HfPriceRuleItem.price_version_id == version_id))
            for item in items:
                values = item.model_dump()
                for name in ('unit_quantity', 'unit_price', 'quantity_from', 'quantity_to'):
                    if values[name] is not None:
                        values[name] = Decimal(values[name])
                db.add(HfPriceRuleItem(price_version_id=version_id, **values, **audit))
        if sources is not None:
            await db.execute(delete(HfPriceVersionSource).where(HfPriceVersionSource.price_version_id == version_id))
            for source in sources:
                db.add(HfPriceVersionSource(price_version_id=version_id, source_id=int(source), **audit))
        await db.flush()

    @staticmethod
    async def children(db, ids):
        items = (
            await db.scalars(
                select(HfPriceRuleItem)
                .where(HfPriceRuleItem.price_version_id.in_(ids))
                .order_by(HfPriceRuleItem.item_id)
            )
        ).all()
        sources = (
            await db.scalars(
                select(HfPriceVersionSource)
                .where(HfPriceVersionSource.price_version_id.in_(ids))
                .order_by(HfPriceVersionSource.source_id)
            )
        ).all()
        return items, sources

    @staticmethod
    async def page(db, query):
        statement = select(HfPriceVersion)
        if query.price_book_id:
            statement = statement.where(HfPriceVersion.price_book_id == int(query.price_book_id))
        if query.status:
            statement = statement.where(HfPriceVersion.status == ('0' if query.status == 'draft' else '1'))
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfPriceVersion.price_version_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
                .with_for_update()
            )
        ).all()
        return rows, total

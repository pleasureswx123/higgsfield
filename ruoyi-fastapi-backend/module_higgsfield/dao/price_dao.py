from sqlalchemy import select, func
from module_higgsfield.entity.do.price_do import HfPriceBook
from module_higgsfield.entity.do.model_do import HfModelVariant, HfModelProfileVersion, HfModelProfile
from module_higgsfield.entity.do.provider_do import HfProviderAccount


class PriceDao:
    @staticmethod
    async def variant_scope(db, variant_id):
        return (
            await db.execute(
                select(HfModelVariant, HfModelProfileVersion, HfModelProfile)
                .join(HfModelProfileVersion, HfModelProfileVersion.model_version_id == HfModelVariant.model_version_id)
                .join(HfModelProfile, HfModelProfile.model_id == HfModelProfileVersion.model_id)
                .where(HfModelVariant.variant_id == int(variant_id))
                .with_for_update()
            )
        ).first()

    @staticmethod
    async def account(db, account_id):
        return await db.scalar(
            select(HfProviderAccount).where(HfProviderAccount.account_id == int(account_id)).with_for_update()
        )

    @staticmethod
    async def existing(db, payload):
        return await db.scalar(
            select(HfPriceBook.price_book_id).where(
                HfPriceBook.model_variant_id == int(payload.model_variant_id),
                HfPriceBook.purpose == payload.purpose,
                HfPriceBook.currency == payload.currency,
                HfPriceBook.account_id == (int(payload.account_id) if payload.account_id else None),
            )
        )

    @staticmethod
    async def add(db, values):
        row = HfPriceBook(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def page(db, query):
        statement = select(HfPriceBook)
        for name in ('model_variant_id', 'purpose', 'account_id', 'currency'):
            value = getattr(query, name)
            if value is not None:
                statement = statement.where(
                    getattr(HfPriceBook, name) == (int(value) if name.endswith('_id') else value)
                )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfPriceBook.price_book_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

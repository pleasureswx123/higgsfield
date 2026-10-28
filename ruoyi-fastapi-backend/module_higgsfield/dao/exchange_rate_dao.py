from hashlib import sha256
from sqlalchemy import select, func, or_, and_
from module_higgsfield.entity.do.exchange_rate_do import HfExchangeRateVersion


class ExchangeRateDao:
    @staticmethod
    async def applicable(db, source, target, at):
        model = HfExchangeRateVersion
        return (await db.scalars(select(model).where(model.status == '1', model.valid_from <= at,
            or_(model.valid_until.is_(None), model.valid_until > at),
            or_(and_(model.base_currency == source, model.quote_currency == target),
                and_(model.base_currency == target, model.quote_currency == source)))
            .order_by(model.exchange_rate_id).limit(2))).all()

    @staticmethod
    async def lock_pair(db, base, quote):
        pair = 'hf:exchange:' + ':'.join(sorted((base, quote)))
        lock_id = int.from_bytes(sha256(pair.encode()).digest()[:8], signed=True)
        await db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    @staticmethod
    async def get(db, identity, lock=False):
        statement = select(HfExchangeRateVersion).where(HfExchangeRateVersion.exchange_rate_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def add(db, values):
        row = HfExchangeRateVersion(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def overlap(db, row):
        model = HfExchangeRateVersion
        statement = select(model.exchange_rate_id).where(
            model.status == '1',
            or_(
                and_(model.base_currency == row.base_currency, model.quote_currency == row.quote_currency),
                and_(model.base_currency == row.quote_currency, model.quote_currency == row.base_currency),
            ),
            or_(model.valid_until.is_(None), model.valid_until > row.valid_from),
        )
        if row.valid_until is not None:
            statement = statement.where(model.valid_from < row.valid_until)
        return await db.scalar(statement.limit(1))

    @staticmethod
    async def page(db, query):
        statement = select(HfExchangeRateVersion)
        for name in ('base_currency', 'quote_currency'):
            value = getattr(query, name)
            if value:
                statement = statement.where(getattr(HfExchangeRateVersion, name) == value)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfExchangeRateVersion.exchange_rate_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

from sqlalchemy import select, func, or_
from module_higgsfield.entity.do.budget_do import HfBudgetPeriod, HfBudgetLedgerEntry


class BudgetPeriodDao:
    @staticmethod
    async def get(db, identity, lock=False):
        statement = select(HfBudgetPeriod).where(HfBudgetPeriod.period_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def conflict(db, budget, start, end, total=False):
        statement = select(HfBudgetPeriod.period_id).where(HfBudgetPeriod.budget_id == budget)
        if not total:
            statement = statement.where(or_(HfBudgetPeriod.period_end.is_(None), HfBudgetPeriod.period_end > start))
            if end is not None:
                statement = statement.where(HfBudgetPeriod.period_start < end)
        return await db.scalar(statement.limit(1))

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def page(db, identity, query, ledger=False):
        model = HfBudgetLedgerEntry if ledger else HfBudgetPeriod
        statement = (
            select(model).where(model.period_id == int(identity))
            if ledger
            else select(model).where(model.budget_id == int(identity))
        )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        order = model.entry_id if ledger else model.period_id
        rows = (
            await db.scalars(
                statement.order_by(order.desc()).offset((query.page_num - 1) * query.page_size).limit(query.page_size)
            )
        ).all()
        return rows, total

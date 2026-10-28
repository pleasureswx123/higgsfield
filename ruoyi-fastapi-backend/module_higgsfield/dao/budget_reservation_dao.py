from sqlalchemy import select, or_
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod, HfBudgetReservation, HfBudgetLedgerEntry
from module_higgsfield.entity.do.job_do import HfCreationJob


class BudgetReservationDao:
    @staticmethod
    async def definition(db, identity):
        return await db.get(HfBudget, identity)

    @staticmethod
    async def ledger_event(db, period_id, key):
        return await db.scalar(
            select(HfBudgetLedgerEntry).where(
                HfBudgetLedgerEntry.period_id == period_id, HfBudgetLedgerEntry.business_event_key == key
            )
        )

    @staticmethod
    async def billing_facts(db, job_id, purpose):
        from module_higgsfield.entity.do.billing_do import HfBillingEvent
        from module_higgsfield.entity.do.usage_do import HfBillingSubject

        return (
            await db.execute(
                select(HfBillingSubject.subject_id, HfBillingEvent)
                .outerjoin(
                    HfBillingEvent,
                    (HfBillingEvent.subject_id == HfBillingSubject.subject_id) & (HfBillingEvent.purpose == purpose),
                )
                .where(HfBillingSubject.job_id == job_id)
                .order_by(HfBillingSubject.subject_id)
            )
        ).all()

    @staticmethod
    async def release_context(db, job_id):
        job = await db.scalar(
            select(HfCreationJob)
            .where(HfCreationJob.job_id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        period_ids = list(
            (await db.scalars(select(HfBudgetReservation.period_id).where(HfBudgetReservation.job_id == job_id))).all()
        )
        periods = list(
            (
                await db.scalars(
                    select(HfBudgetPeriod)
                    .where(HfBudgetPeriod.period_id.in_(period_ids))
                    .order_by(HfBudgetPeriod.period_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        reservations = list(
            (
                await db.scalars(
                    select(HfBudgetReservation)
                    .where(HfBudgetReservation.job_id == job_id)
                    .order_by(HfBudgetReservation.period_id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()
        )
        return job, {period.period_id: period for period in periods}, reservations

    @staticmethod
    async def budgets(db, project_id, user_id):
        return (
            await db.scalars(
                select(HfBudget)
                .where(or_(HfBudget.project_id == project_id, HfBudget.user_id == user_id), HfBudget.active == 'Y')
                .order_by(HfBudget.budget_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()

    @staticmethod
    async def periods(db, budget_ids, at):
        return (
            await db.scalars(
                select(HfBudgetPeriod)
                .where(
                    HfBudgetPeriod.budget_id.in_(budget_ids),
                    HfBudgetPeriod.period_start <= at,
                    or_(HfBudgetPeriod.period_end.is_(None), HfBudgetPeriod.period_end > at),
                )
                .order_by(HfBudgetPeriod.period_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()

    @staticmethod
    async def existing_job(db, job_id):
        return await db.scalar(
            select(HfBudgetReservation.reservation_id).where(HfBudgetReservation.job_id == job_id).limit(1)
        )

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

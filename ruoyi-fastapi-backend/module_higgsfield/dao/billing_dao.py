"""计价事实访问；调用服务先锁任务，再锁计费对象。"""

from sqlalchemy import select, func, text
from module_higgsfield.dao.budget_dao import BudgetDao

from module_higgsfield.entity.do.billing_do import HfBillingEvent, HfBillingAdjustment, HfBillingLineItem
from module_higgsfield.entity.do.price_do import HfPriceBook, HfPriceVersion, HfPriceRuleItem
from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from module_higgsfield.entity.do.job_do import HfCreationJob


class BillingDao:
    @staticmethod
    async def page(db, actor, roles, query):
        scope, params = BudgetDao.scope(actor, roles)
        sql = (
            ' FROM hf_billing_event e JOIN hf_billing_subject s ON s.subject_id=e.subject_id '
            'JOIN hf_creation_job j ON j.job_id=s.job_id JOIN hf_project p ON p.project_id=j.project_id '
            "JOIN sys_user u ON u.user_id=p.create_user_id WHERE p.del_flag='0' AND u.del_flag='0' AND " + scope
        )
        if query.scope == 'cost_center':
            sql = (' FROM hf_billing_event e JOIN hf_billing_subject s ON s.subject_id=e.subject_id '
                'WHERE s.job_id IS NULL AND s.cost_center_id IS NOT NULL AND '
                + ('TRUE' if any(role['data_scope'] == '1' for role in roles) else 'FALSE'))
        params['purpose'] = query.purpose
        sql += ' AND e.purpose=:purpose'
        if query.cost_center_id is not None:
            sql += ' AND s.cost_center_id=:cost_center_id'
            params['cost_center_id'] = int(query.cost_center_id)
        for key, column in (
            ('currency', 'e.currency'),
            ('project_id', 'j.project_id'),
            ('job_id', 'j.job_id'),
            ('user_id', 'j.actor_id'),
        ):
            value = getattr(query, key)
            if value is not None:
                sql += f' AND {column}=:{key}'
                params[key] = int(value) if key.endswith('_id') else value
        if query.from_time is not None:
            sql += ' AND e.create_time>=:from_time'
            params['from_time'] = query.from_time
        if query.to_time is not None:
            sql += ' AND e.create_time<:to_time'
            params['to_time'] = query.to_time
        if query.state is not None:
            sql += ' AND e.state=:state'
            params['state'] = str(('pending', 'calculated', 'confirmed', 'disputed').index(query.state))
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(offset=(query.page_num - 1) * query.page_size, limit=query.page_size)
        rows = (
            (
                await db.execute(
                    text(
                        'SELECT e.*,s.job_id,s.cost_center_id,'
                        '(SELECT coalesce(sum(a.delta_amount),0) FROM hf_billing_adjustment a WHERE a.event_id=e.event_id) AS adjustment_total'
                        + sql
                        + ' ORDER BY e.event_id DESC OFFSET :offset LIMIT :limit'
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return rows, total

    @staticmethod
    async def lines(db, identity):
        return (
            await db.scalars(
                select(HfBillingLineItem)
                .where(HfBillingLineItem.event_id == identity)
                .order_by(HfBillingLineItem.line_item_id)
            )
        ).all()

    @staticmethod
    async def refresh(db, row):
        await db.refresh(row)

    @staticmethod
    async def context(db, identity):
        return (
            await db.execute(
                select(HfBillingEvent, HfBillingSubject)
                .join(HfBillingSubject, HfBillingSubject.subject_id == HfBillingEvent.subject_id)
                .where(HfBillingEvent.event_id == identity)
            )
        ).first()

    @staticmethod
    async def event_by_id(db, identity):
        return await db.scalar(
            select(HfBillingEvent)
            .where(HfBillingEvent.event_id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def adjustment_by_key(db, identity, key):
        return await db.scalar(
            select(HfBillingAdjustment).where(
                HfBillingAdjustment.event_id == identity, HfBillingAdjustment.adjustment_key == key
            )
        )

    @staticmethod
    async def adjustments(db, identity):
        return (
            await db.scalars(
                select(HfBillingAdjustment)
                .where(HfBillingAdjustment.event_id == identity)
                .order_by(HfBillingAdjustment.adjustment_id)
            )
        ).all()

    @staticmethod
    async def adjustment_total(db, identity):
        return await db.scalar(
            select(func.coalesce(func.sum(HfBillingAdjustment.delta_amount), 0)).where(
                HfBillingAdjustment.event_id == identity
            )
        )

    @staticmethod
    async def adopted_usage(db, identity):
        return await db.get(HfUsageRecord, identity) if identity is not None else None

    @staticmethod
    async def now(db):
        return await db.scalar(select(func.clock_timestamp()))

    @staticmethod
    async def candidates(db, after, limit):
        return (
            await db.scalars(
                select(HfBillingSubject.job_id)
                .where(HfBillingSubject.job_id > after, HfBillingSubject.subject_kind == 'generation')
                .distinct()
                .order_by(HfBillingSubject.job_id)
                .limit(limit)
            )
        ).all()

    @staticmethod
    async def job(db, identity, skip_locked=True):
        return await db.scalar(
            select(HfCreationJob)
            .where(HfCreationJob.job_id == identity)
            .with_for_update(skip_locked=skip_locked)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def subjects(db, identity):
        return (
            await db.scalars(
                select(HfBillingSubject.subject_id)
                .where(HfBillingSubject.job_id == identity, HfBillingSubject.subject_kind == 'generation')
                .order_by(HfBillingSubject.subject_id)
            )
        ).all()

    @staticmethod
    async def subject(db, identity):
        return await db.scalar(
            select(HfBillingSubject).where(HfBillingSubject.subject_id == identity).with_for_update()
        )

    @staticmethod
    async def evidence(db, identity):
        return (
            await db.scalars(
                select(HfUsageRecord).where(HfUsageRecord.subject_id == identity).order_by(HfUsageRecord.revision_no)
            )
        ).all()

    @staticmethod
    async def event(db, identity, purpose):
        return await db.scalar(
            select(HfBillingEvent)
            .where(HfBillingEvent.subject_id == identity, HfBillingEvent.purpose == purpose)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def price(db, identity):
        scope = (
            await db.execute(
                select(HfPriceVersion, HfPriceBook)
                .join(HfPriceBook, HfPriceBook.price_book_id == HfPriceVersion.price_book_id)
                .where(HfPriceVersion.price_version_id == identity)
            )
        ).first()
        items = (
            await db.scalars(
                select(HfPriceRuleItem)
                .where(HfPriceRuleItem.price_version_id == identity)
                .order_by(HfPriceRuleItem.item_id)
            )
        ).all()
        return scope, items

    @staticmethod
    async def add(db, model, values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row

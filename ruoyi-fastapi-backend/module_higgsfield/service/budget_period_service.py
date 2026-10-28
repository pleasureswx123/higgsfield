"""额度变动与账本同事务；不以降额清除消费或预占。"""

from datetime import datetime
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo
from common.vo import PageModel
from module_higgsfield.dao.budget_dao import BudgetDao
from module_higgsfield.dao.budget_period_dao import BudgetPeriodDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.entity.do.budget_do import HfBudgetPeriod, HfBudgetLedgerEntry
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class BudgetPeriodService:
    fail = staticmethod(WorkspaceService.conflict)

    @staticmethod
    def result(row):
        with localcontext() as context:
            context.prec = 100
            available = row.limit_amount - row.reserved_amount - row.consumed_amount
        return {
            'id': str(row.period_id),
            'budgetId': str(row.budget_id),
            'periodStart': row.period_start.isoformat(),
            'periodEnd': row.period_end.isoformat() if row.period_end else None,
            'limitAmount': format(row.limit_amount, '.10f'),
            'reservedAmount': format(row.reserved_amount, '.10f'),
            'consumedAmount': format(row.consumed_amount, '.10f'),
            'availableAmount': format(available, '.10f'),
            'revision': str(row.revision),
        }

    @staticmethod
    def ledger(row):
        snapshot = row.conversion_snapshot or {}
        # 仅公开计价审计字段，未来内部快照扩展不能自动透传到管理界面。
        conversion = {key: snapshot[key] for key in (
            'sourceCurrency', 'targetCurrency', 'sourceAmount', 'rate', 'direction', 'rawAmount',
            'amount', 'roundingMode', 'calculationScale', 'at', 'previousConvertedAmount',
            'convertedDelta', 'sourceAdjustmentAmount') if key in snapshot}
        return {
            'id': str(row.entry_id),
            'entryType': row.entry_type,
            'businessEventKey': row.business_event_key,
            'reservedDelta': format(row.reserved_delta, '.10f'),
            'consumedDelta': format(row.consumed_delta, '.10f'),
            'limitDelta': format(row.limit_delta, '.10f'),
            'reservationId': str(row.reservation_id) if row.reservation_id is not None else None,
            'billingEventId': str(row.billing_event_id) if row.billing_event_id is not None else None,
            'adjustmentId': str(row.adjustment_id) if row.adjustment_id is not None else None,
            'exchangeRateVersionId': str(row.exchange_rate_version_id) if row.exchange_rate_version_id is not None else None,
            'conversion': conversion if row.exchange_rate_version_id is not None else None,
            'reason': row.reason,
            'createTime': row.create_time.isoformat(),
        }

    @classmethod
    async def authorize(cls, db, user, budget_id, permission, write=False):
        actor, roles = await AdminScopeService.context(db, user, permission)
        budget = await BudgetDao.get(db, budget_id)
        if budget is None:
            cls.fail('BUDGET_NOT_FOUND', '预算不存在或不在管理范围内')
        if budget.purpose == 'procurement' and not any(role['data_scope'] == '1' for role in roles):
            cls.fail('BUDGET_NOT_FOUND', '预算不存在或不在管理范围内')
        kind, identity = ('project', budget.project_id) if budget.project_id else ('user', budget.user_id)
        if write:
            await BudgetDao.lock_subject(db, kind, identity)
        if await BudgetDao.subject(db, kind, identity, actor, roles) is None:
            cls.fail('BUDGET_NOT_FOUND', '预算不存在或不在管理范围内')
        return await BudgetDao.get(db, budget_id, lock=True) if write else budget

    @classmethod
    def validate_period(cls, budget, payload):
        if budget.cycle_kind == 'total':
            if payload.period_end is not None:
                cls.fail('BUDGET_TOTAL_PERIOD_INVALID', '总额预算周期不能设置结束时间')
            return
        local = payload.period_start.astimezone(ZoneInfo(budget.business_timezone))
        if (local.day, local.hour, local.minute, local.second, local.microsecond) != (1, 0, 0, 0, 0):
            cls.fail('BUDGET_MONTH_BOUNDARY_INVALID', '月度预算起点必须为业务时区自然月起点')
        expected = datetime(
            local.year + int(local.month == 12), 1 if local.month == 12 else local.month + 1, 1, tzinfo=local.tzinfo
        )
        if payload.period_end is None or payload.period_end != expected:
            cls.fail('BUDGET_MONTH_BOUNDARY_INVALID', '月度预算终点必须为下一自然月起点')

    @classmethod
    async def listing(cls, db, user, identity, query, ledger=False):
        if ledger:
            period = await BudgetPeriodDao.get(db, identity)
            if period is None:
                cls.fail('BUDGET_PERIOD_NOT_FOUND', '预算周期不存在或不在管理范围内')
            budget_id = period.budget_id
        else:
            budget_id = identity
        await cls.authorize(db, user, budget_id, 'billing:read' if ledger else 'billing:budget:read')
        rows, total = await BudgetPeriodDao.page(db, identity, query, ledger)
        return PageModel(
            rows=[cls.ledger(row) if ledger else cls.result(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, identity, payload, key, adjust=False):
        path = f'/budget-periods/{identity}/adjust-limit' if adjust else f'/budgets/{identity}/periods'
        prefix = '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            # 先检查功能权限，避免不存在的周期成为无权限探测入口。
            await AdminScopeService.context(db, user, 'billing:budget')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            period = await BudgetPeriodDao.get(db, identity) if adjust else None
            if adjust and period is None:
                cls.fail('BUDGET_PERIOD_NOT_FOUND', '预算周期不存在或不在管理范围内')
            budget = await cls.authorize(
                db, user, period.budget_id if adjust else identity, 'billing:budget', write=True
            )
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            before = None
            with localcontext() as context:
                context.prec = 100
                if adjust:
                    period = await BudgetPeriodDao.get(db, identity, lock=True)
                    WorkspaceService.check_revision(period, payload.revision)
                    before = cls.result(period)
                    new_limit = Decimal(payload.new_limit)
                    delta = new_limit - period.limit_amount
                    period.limit_amount = new_limit
                    period.revision += 1
                    period.update_by, period.update_time = audit['update_by'], audit['update_time']
                else:
                    cls.validate_period(budget, payload)
                    if await BudgetPeriodDao.conflict(
                        db, budget.budget_id, payload.period_start, payload.period_end, budget.cycle_kind == 'total'
                    ):
                        cls.fail('BUDGET_PERIOD_OVERLAP', '预算周期重叠或总额周期已存在')
                    delta = Decimal(payload.limit_amount)
                    period = await BudgetPeriodDao.add(
                        db,
                        HfBudgetPeriod,
                        budget_id=budget.budget_id,
                        period_start=payload.period_start,
                        period_end=payload.period_end,
                        limit_amount=delta,
                        **audit,
                    )
            if delta != 0:
                await BudgetPeriodDao.add(
                    db,
                    HfBudgetLedgerEntry,
                    period_id=period.period_id,
                    business_event_key=f'limit:{period.period_id}:revision:{period.revision}',
                    entry_type='change_limit',
                    reserved_delta=Decimal(0),
                    consumed_delta=Decimal(0),
                    limit_delta=delta,
                    reason=payload.reason,
                    **audit,
                )
            after = cls.result(period)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    project_id=budget.project_id,
                    object_type='budget_period',
                    object_id=str(period.period_id),
                    action='adjust_limit' if adjust else 'create',
                    reason=payload.reason,
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'before': before, 'after': after},
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'budget_period', period.period_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

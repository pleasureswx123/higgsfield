"""供任务受理事务调用的预算预占，不独立提交事务或开放公共接口。"""

from decimal import Decimal, localcontext, ROUND_CEILING
from module_higgsfield.dao.exchange_rate_dao import ExchangeRateDao
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from module_higgsfield.dao.budget_dao import BudgetDao
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from module_higgsfield.entity.do.budget_do import HfBudgetReservation, HfBudgetLedgerEntry
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.price_calculation_service import decimal_value


class BudgetReservationService:
    @classmethod
    async def plan(cls, db, user, *, project_id, at, amounts, missing_budget_policy):
        if missing_budget_policy not in ('allow', 'reject'):
            raise ValueError('必须显式指定无预算策略')
        for kind, identity in sorted((('project', project_id), ('user', user.user.user_id))):
            await BudgetDao.lock_subject(db, kind, identity)
        budgets = await BudgetReservationDao.budgets(db, project_id, user.user.user_id)
        if not budgets:
            if missing_budget_policy == 'reject':
                WorkspaceService.conflict('BUDGET_REQUIRED', '当前没有适用预算')
            return []
        periods = await BudgetReservationDao.periods(db, [row.budget_id for row in budgets], at)
        by_budget = {}
        for period in periods:
            if period.budget_id in by_budget:
                WorkspaceService.conflict('BUDGET_PERIOD_AMBIGUOUS', '预算存在重叠周期，不能受理')
            by_budget[period.budget_id] = period
        planned = []
        with localcontext() as context:
            context.prec = 100
            for budget in budgets:
                period = by_budget.get(budget.budget_id)
                if period is None:
                    WorkspaceService.conflict('BUDGET_PERIOD_REQUIRED', '启用预算缺少受理时点对应周期')
                amount = amounts.get((budget.purpose, budget.currency))
                conversion = {}
                if amount is None:
                    candidates = [(currency, value) for (purpose, currency), value in amounts.items()
                        if purpose == budget.purpose]
                    if len(candidates) != 1:
                        WorkspaceService.conflict('BUDGET_ESTIMATE_REQUIRED', '缺少唯一对应预算用途的可靠原币预估')
                    source, original = candidates[0]
                    rates = await ExchangeRateDao.applicable(db, source, budget.currency, at)
                    if len(rates) != 1:
                        WorkspaceService.conflict('BUDGET_EXCHANGE_RATE_REQUIRED', '受理时点缺少唯一已发布汇率')
                    conversion = ExchangeRateService.convert(rates[0], format(original, 'f'), source,
                        budget.currency, at=at, scale=10)
                    amount = Decimal(conversion['rawAmount']).quantize(Decimal('0.0000000001'), rounding=ROUND_CEILING)
                    if amount >= Decimal('100000000000000'):
                        WorkspaceService.conflict('BUDGET_ESTIMATE_REQUIRED', '换算预占金额超过存储范围')
                    conversion = {**conversion, 'amount': format(amount, '.10f'), 'roundingMode': 'ceiling'}
                if period.limit_amount - period.reserved_amount - period.consumed_amount < amount:
                    WorkspaceService.conflict('BUDGET_INSUFFICIENT', '至少一项适用预算可用额度不足')
                planned.append((period, amount, budget, conversion))
        return planned

    @classmethod
    async def reserve(cls, db, user, *, job_id, project_id, at, estimates, missing_budget_policy):
        """调用方须先完成任务鉴权及任务锁，将任务、快照和 Outbox 与本结果一起提交。

        estimates 的键为 (purpose,currency)，值为已验证的保守预估十进制金额。
        跨币种按受理时点唯一已发布汇率换算，向上舍入；返回快照供任务事务固化。
        重试须由外层任务幂等记录重放，不能以再次调用本方法重新选当前周期。
        """
        if missing_budget_policy not in ('reject', 'allow'):
            raise ValueError('必须显式指定无预算策略')
        if (
            at.tzinfo is None
            or type(job_id) is not int
            or not 0 < job_id <= 9223372036854775807
            or type(project_id) is not int
            or project_id <= 0
        ):
            raise ValueError('任务、项目及受理时点无效')
        amounts = {}
        for key, value in estimates.items():
            if (
                not isinstance(key, tuple)
                or len(key) != 2
                or key[0] not in ('platform', 'procurement')
                or not isinstance(key[1], str)
                or len(key[1]) != 3
                or not key[1].isascii()
                or not key[1].isupper()
                or not key[1].isalpha()
            ):
                raise ValueError('预估必须明确用途和币种')
            amounts[key] = decimal_value(value, 24, 10)
        # 保存点保障任一周期写入失败时，本次预占整体撤销；外层仍须管理任务事务。
        async with db.begin_nested():
            for kind, identity in sorted((('project', project_id), ('user', user.user.user_id))):
                await BudgetDao.lock_subject(db, kind, identity)
            if await BudgetReservationDao.existing_job(db, job_id):
                WorkspaceService.conflict('BUDGET_RESERVATION_EXISTS', '任务已有预算预占，必须重放原受理结果')
            planned = await cls.plan(
                db, user, project_id=project_id, at=at, amounts=amounts, missing_budget_policy=missing_budget_policy
            )
            with localcontext() as context:
                context.prec = 100
                audit = WriteService.audit(user)
                result = []
                for period, amount, budget, conversion in sorted(planned, key=lambda value: value[0].period_id):
                    row = await BudgetReservationDao.add(
                        db,
                        HfBudgetReservation,
                        job_id=job_id,
                        period_id=period.period_id,
                        original_amount=amount,
                        remaining_amount=amount,
                        **audit,
                    )
                    if amount:
                        period.reserved_amount += amount
                        period.revision += 1
                        period.update_by, period.update_time = audit['update_by'], audit['update_time']
                        await BudgetReservationDao.add(
                            db,
                            HfBudgetLedgerEntry,
                            period_id=period.period_id,
                            reservation_id=row.reservation_id,
                            business_event_key=f'job:{job_id}:reserve',
                            entry_type='reserve',
                            reserved_delta=amount,
                            consumed_delta=Decimal(0),
                            limit_delta=Decimal(0),
                            reason='任务受理预占',
                            exchange_rate_version_id=int(conversion['exchangeRateVersionId']) if conversion else None,
                            conversion_snapshot=conversion,
                            **audit,
                        )
                    result.append(
                        {
                            'id': str(row.reservation_id),
                            'periodId': str(period.period_id),
                            'budgetId': str(budget.budget_id),
                            'purpose': budget.purpose,
                            'currency': budget.currency,
                            'originalAmount': format(amount, '.10f'),
                            'conversion': conversion,
                            'state': 'reserved',
                        }
                    )
                await db.flush()
                return result

"""首次费用按原预占期间入账；未知费用保留预占，调整另走追加分录。"""

from decimal import Decimal, localcontext
from datetime import datetime
from module_higgsfield.dao.exchange_rate_dao import ExchangeRateDao
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao as Dao
from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.entity.do.budget_do import HfBudgetLedgerEntry


class BudgetSettlementService:
    @staticmethod
    async def fixed_conversion(db, job, reservation, period, budget):
        """只读取受理时固化的依据，禁止在结算时补选当前汇率。"""
        entries = [row for row in job.input_snapshot.get('budgetReservations', [])
            if row.get('id') == str(reservation.reservation_id) and row.get('periodId') == str(period.period_id)]
        snapshot = entries[0].get('conversion', {}) if len(entries) == 1 else {}
        if not snapshot:
            initial = await Dao.ledger_event(db, period.period_id, f'job:{job.job_id}:reserve')
            snapshot = initial.conversion_snapshot if initial else {}
        if not snapshot:
            return None
        rate = await ExchangeRateDao.get(db, snapshot['exchangeRateVersionId'])
        if rate is None or snapshot['targetCurrency'] != budget.currency:
            raise ValueError('预占固定汇率证据不完整')
        at = datetime.fromisoformat(snapshot['at'])
        verified = ExchangeRateService.convert(rate, snapshot['sourceAmount'], snapshot['sourceCurrency'],
            budget.currency, at=at, scale=10)
        if Decimal(verified['rate']) != Decimal(snapshot['rate']) or verified['direction'] != snapshot['direction']:
            raise ValueError('预占汇率与历史版本不一致')
        return rate, at, snapshot['sourceCurrency']

    @staticmethod
    def converted(amount, source, target, fixed):
        if not amount.is_finite() or amount < 0:
            raise ValueError('费用金额无效')
        if source == target:
            return amount, {}
        if fixed is None or fixed[2] != source:
            return None
        snapshot = ExchangeRateService.convert(fixed[0], format(amount, 'f'), source, target,
            at=fixed[1], scale=10)
        return Decimal(snapshot['amount']), snapshot

    @classmethod
    async def settle(cls, db, job_id, *, now, worker):
        """调用方统一提交计价、预算与任务事件；本方法不独立提交。"""
        job, periods, reservations = await Dao.release_context(db, job_id)
        if job is None:
            raise ValueError('结算任务不存在')
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        changed = False
        with localcontext() as context:
            context.prec = 100
            for reservation in reservations:
                if reservation.state == '3':
                    # 已确认未提交并释放的任务不能自动重新扣费。
                    continue
                period = periods.get(reservation.period_id)
                if period is None:
                    raise ValueError('原预占周期缺失')
                budget = await Dao.definition(db, period.budget_id)
                if budget is None:
                    raise ValueError('原预算定义缺失')
                if (budget.project_id is not None and budget.project_id != job.project_id) or (
                    budget.user_id is not None and budget.user_id != job.actor_id
                ):
                    raise ValueError('原预占预算不属于任务项目或执行用户')
                facts = await Dao.billing_facts(db, job_id, budget.purpose)
                fixed = await cls.fixed_conversion(db, job, reservation, period, budget)
                complete = bool(facts) and job.orchestration_state == '5'
                touched = False
                for _, event in facts:
                    if (
                        event is None
                        or event.state not in {'1', '2'}
                        or event.amount is None
                    ):
                        complete = False
                        continue
                    converted = cls.converted(event.amount, event.currency, budget.currency, fixed)
                    if converted is None:
                        complete = False
                        continue
                    amount, conversion = converted
                    key = f'billing:{event.event_id}:settle'
                    if await Dao.ledger_event(db, period.period_id, key):
                        continue
                    if not amount.is_finite() or amount < 0:
                        raise ValueError('费用金额无效')
                    released = min(reservation.remaining_amount, amount)
                    if period.reserved_amount < released:
                        raise ValueError('预占余额缓存不一致')
                    if not amount and not released:
                        continue
                    period.reserved_amount -= released
                    period.consumed_amount += amount
                    reservation.remaining_amount -= released
                    await Dao.add(
                        db,
                        HfBudgetLedgerEntry,
                        period_id=period.period_id,
                        reservation_id=reservation.reservation_id,
                        billing_event_id=event.event_id,
                        business_event_key=key,
                        entry_type='settle',
                        reserved_delta=-released,
                        consumed_delta=amount,
                        limit_delta=Decimal(0),
                        reason='固定价格首次费用结算',
                        exchange_rate_version_id=int(conversion['exchangeRateVersionId']) if conversion else None,
                        conversion_snapshot=conversion,
                        **audit,
                    )
                    touched = True
                for _, event in facts:
                    if event is None or event.amount is None or event.state not in {'1', '2'}:
                        continue
                    converted = cls.converted(event.amount, event.currency, budget.currency, fixed)
                    if converted is None:
                        continue
                    previous_amount, _ = converted
                    initial = await Dao.ledger_event(db, period.period_id, f'billing:{event.event_id}:settle')
                    if initial is None and previous_amount != 0:
                        continue
                    effective = event.amount
                    for adjustment in await BillingDao.adjustments(db, event.event_id):
                        delta = adjustment.delta_amount
                        if not delta.is_finite() or delta == 0:
                            raise ValueError('费用调整金额无效')
                        effective += delta
                        if effective < 0:
                            raise ValueError('费用调整不能使单事件有效金额为负')
                        current_amount, conversion = cls.converted(effective, event.currency, budget.currency, fixed)
                        # 按累计有效金额换算后的差额记账，避免逐笔舍入失去守恒。
                        delta = current_amount - previous_amount
                        if conversion:
                            conversion = {**conversion, 'previousConvertedAmount': format(previous_amount, '.10f'),
                                'convertedDelta': format(delta, '.10f'), 'sourceAdjustmentAmount': format(adjustment.delta_amount, '.10f')}
                        previous_amount = current_amount
                        key = f'adjustment:{adjustment.adjustment_id}:settle'
                        if await Dao.ledger_event(db, period.period_id, key):
                            continue
                        if not delta:
                            continue
                        if period.consumed_amount + delta < 0:
                            raise ValueError('费用调整不能使周期已消费金额为负')
                        await Dao.add(
                            db,
                            HfBudgetLedgerEntry,
                            period_id=period.period_id,
                            reservation_id=reservation.reservation_id,
                            billing_event_id=event.event_id,
                            adjustment_id=adjustment.adjustment_id,
                            business_event_key=key,
                            entry_type='adjust',
                            reserved_delta=Decimal(0),
                            consumed_delta=delta,
                            limit_delta=Decimal(0),
                            reason=adjustment.reason,
                            exchange_rate_version_id=int(conversion['exchangeRateVersionId']) if conversion else None,
                            conversion_snapshot=conversion,
                            **audit,
                        )
                        period.consumed_amount += delta
                        touched = True
                if complete and reservation.remaining_amount:
                    remainder = reservation.remaining_amount
                    if period.reserved_amount < remainder:
                        raise ValueError('预占余额缓存不一致')
                    await Dao.add(
                        db,
                        HfBudgetLedgerEntry,
                        period_id=period.period_id,
                        reservation_id=reservation.reservation_id,
                        business_event_key=f'job:{job_id}:settlement-remainder',
                        entry_type='release',
                        reserved_delta=-remainder,
                        consumed_delta=Decimal(0),
                        limit_delta=Decimal(0),
                        reason='任务费用完整后的预占尾差释放',
                        **audit,
                    )
                    period.reserved_amount -= remainder
                    reservation.remaining_amount = Decimal(0)
                    touched = True
                state = '2' if complete else '4'
                if touched:
                    period.revision += 1
                    period.update_by, period.update_time = worker, now
                if touched or reservation.state != state:
                    reservation.state = state
                    reservation.revision += 1
                    reservation.update_by, reservation.update_time = worker, now
                    changed = True
            await db.flush()
        return changed

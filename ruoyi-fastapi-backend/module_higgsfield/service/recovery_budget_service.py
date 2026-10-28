"""恢复预算守恒与依据只读检查，只报告记录编号及规则，不覆盖账本或余额。"""

from collections import Counter
from datetime import datetime
from decimal import Decimal, DecimalException, ROUND_CEILING, localcontext
from types import SimpleNamespace
from sqlalchemy import text
from module_higgsfield.dao.recovery_budget_dao import RecoveryBudgetDao
from module_higgsfield.service.exchange_rate_service import ExchangeRateService


class RecoveryBudgetService:
    @staticmethod
    def conversion_valid(row):
        """按历史版本重新计算，预占向上舍入，调整按累计金额差额入账。"""
        try:
            saved = row['conversion_snapshot']
            if not isinstance(saved, dict) or row['exchange_rate_id'] is None:
                return False
            if (saved['exchangeRateVersionId'] != str(row['exchange_rate_version_id'])
                    or saved['targetCurrency'] != row['budget_currency']
                    or type(saved['calculationScale']) is not int or saved['calculationScale'] != 10):
                return False
            rate = SimpleNamespace(**row)
            at = datetime.fromisoformat(saved['at'])
            computed = ExchangeRateService.convert(rate, saved['sourceAmount'],
                saved['sourceCurrency'], saved['targetCurrency'], at=at, scale=10)
            with localcontext() as context:
                context.prec = 100
                if row['entry_type'] == 'reserve':
                    computed['amount'] = format(Decimal(computed['rawAmount']).quantize(
                        Decimal('0.0000000001'), rounding=ROUND_CEILING), 'f')
                    computed['roundingMode'] = 'ceiling'
                    delta = row['reserved_delta']
                elif row['entry_type'] == 'settle':
                    delta = row['consumed_delta']
                elif row['entry_type'] == 'adjust':
                    adjustment = Decimal(saved['sourceAdjustmentAmount'])
                    if not adjustment.is_finite() or adjustment == 0:
                        return False
                    previous = ExchangeRateService.convert(rate,
                        format(Decimal(saved['sourceAmount']) - adjustment, 'f'),
                        saved['sourceCurrency'], saved['targetCurrency'], at=at, scale=10)
                    delta = Decimal(computed['amount']) - Decimal(previous['amount'])
                    if (Decimal(saved['previousConvertedAmount']) != Decimal(previous['amount'])
                            or Decimal(saved['convertedDelta']) != delta or delta != row['consumed_delta']):
                        return False
                    delta = Decimal(computed['amount'])
                else:
                    return False
                return (saved['direction'] == computed['direction']
                        and saved['roundingMode'] == computed['roundingMode']
                        and all(isinstance(saved[key], str) and Decimal(saved[key]).is_finite()
                            and Decimal(saved[key]) == Decimal(computed[key])
                            for key in ('rate', 'rawAmount', 'amount'))
                        and Decimal(computed['amount']) == delta)
        except (KeyError, ValueError, TypeError, DecimalException):
            return False

    @staticmethod
    async def audit(sessions, *, page_size=200, sample_limit=100):
        if not 1 <= page_size <= 500 or not 0 <= sample_limit <= 1000:
            raise ValueError('核验分页或样本数量不合法')
        rules = ('limit_ledger_mismatch', 'reserved_ledger_mismatch',
                 'consumed_ledger_mismatch', 'reservation_balance_mismatch')
        counts, failures, after_id, total = Counter({rule: 0 for rule in rules}), [], 0, 0
        while True:
            async with sessions() as db:
                await db.execute(text('SET TRANSACTION READ ONLY'))
                rows = await RecoveryBudgetDao.page(db, after_id, page_size)
            if not rows:
                break
            total += len(rows)
            for row in rows:
                for rule in rules:
                    if row[rule]:
                        counts[rule] += 1
                        if len(failures) < sample_limit:
                            failures.append({'periodId': str(row['period_id']), 'rule': rule})
            after_id = rows[-1]['period_id']
        # 独立扫描引用源表，不让不存在周期中的孤立记录从余额分页消失。
        async with sessions() as db:
            await db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            for rule in RecoveryBudgetDao.REFERENCE_RULES:
                count, ids = await RecoveryBudgetDao.references(db, rule, sample_limit - len(failures))
                counts[rule] = count
                failures.extend({'recordId': str(identity), 'rule': rule} for identity in ids)
        counts['ledger_conversion_invalid'] = 0
        after_id = 0
        while True:
            async with sessions() as db:
                await db.execute(text('SET TRANSACTION READ ONLY'))
                rows = await RecoveryBudgetDao.conversions(db, after_id, page_size)
            if not rows:
                break
            for row in rows:
                if not RecoveryBudgetService.conversion_valid(row):
                    counts['ledger_conversion_invalid'] += 1
                    if len(failures) < sample_limit:
                        failures.append({'recordId': str(row['entry_id']), 'rule': 'ledger_conversion_invalid'})
            after_id = rows[-1]['entry_id']
        failed = sum(counts.values())
        return {'scope': 'budget_period_conservation', 'complete': True, 'total': total,
                'failed': failed, 'counts': dict(counts), 'failures': failures,
                'failuresTruncated': failed > len(failures)}

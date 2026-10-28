"""费用汇总纯计算：调用方先完成数据范围与时间过滤，输入每事件一行。"""

from dataclasses import dataclass
from decimal import Decimal, localcontext
import re


@dataclass(frozen=True)
class UsageSummaryFact:
    event_id: int
    subject_id: int
    group_key: str
    display_name: str
    purpose: str
    currency: str
    state: str
    amount: Decimal | None
    adjustment_total: Decimal = Decimal(0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    video_tokens: int | None = None
    usage_completeness: str = 'unknown'


class UsageSummaryCalculationService:
    buckets = {'1': 'calculatedAmount', '2': 'confirmedAmount', '3': 'disputedAmount'}

    @classmethod
    def summarize(cls, facts, *, purpose):
        if purpose not in {'platform', 'procurement'}:
            raise ValueError('汇总必须明确单一计价用途')
        groups, events, subjects = {}, set(), set()
        with localcontext() as context:
            context.prec = 100
            for fact in facts:
                if fact.event_id in events:
                    raise ValueError('汇总包含重复费用事件，不能重复累计')
                events.add(fact.event_id)
                if fact.purpose != purpose or not re.fullmatch(r'[A-Z]{3}', fact.currency):
                    raise ValueError('汇总用途或币种不合法')
                if fact.state not in {'0', '1', '2', '3'}:
                    raise ValueError('费用状态无效')
                if fact.usage_completeness not in {'available', 'partial', 'unknown'}:
                    raise ValueError('用量完整性无效')
                for amount in (fact.amount, fact.adjustment_total):
                    if amount is not None and (not isinstance(amount, Decimal) or not amount.is_finite()):
                        raise ValueError('汇总金额必须为有限Decimal')
                key = (fact.group_key, fact.currency)
                group = groups.setdefault(
                    key,
                    dict(
                        groupKey=fact.group_key,
                        displayName=fact.display_name,
                        currency=fact.currency,
                        calculatedAmount=Decimal(0),
                        confirmedAmount=Decimal(0),
                        disputedAmount=Decimal(0),
                        unknownCount=0,
                        inputTokens=0,
                        outputTokens=0,
                        videoTokens=0,
                        _completeness=[],
                    ),
                )
                if fact.amount is None or fact.state == '0':
                    group['unknownCount'] += 1
                else:
                    effective = fact.amount + fact.adjustment_total
                    if effective < 0:
                        raise ValueError('事件有效金额不能为负')
                    group[cls.buckets[fact.state]] += effective
                # 同一对象同一口径仅应有一个事件；拒绝重复对象，不能叠加用量修订。
                identity = (fact.subject_id, fact.purpose)
                if identity in subjects:
                    raise ValueError('汇总包含重复计费对象')
                subjects.add(identity)
                group['_completeness'].append(fact.usage_completeness)
                for field, value in (
                    ('inputTokens', fact.input_tokens),
                    ('outputTokens', fact.output_tokens),
                    ('videoTokens', fact.video_tokens),
                ):
                    if value is not None:
                        if type(value) is not int or not 0 <= value <= 9223372036854775807:
                            raise ValueError('Token用量必须为非负bigint整数')
                        group[field] += value
            result = []
            for key in sorted(groups):
                group = groups[key]
                states = group.pop('_completeness')
                group['usageCompleteness'] = (
                    'available'
                    if all(state == 'available' for state in states)
                    else 'unknown'
                    if all(state == 'unknown' for state in states)
                    else 'partial'
                )
                group['totalKnownAmount'] = sum((group[name] for name in cls.buckets.values()), Decimal(0))
                for name in (*cls.buckets.values(), 'totalKnownAmount'):
                    group[name] = format(group[name], '.10f')
                for name in ('unknownCount', 'inputTokens', 'outputTokens', 'videoTokens'):
                    group[name] = str(group[name])
                result.append(group)
        return result

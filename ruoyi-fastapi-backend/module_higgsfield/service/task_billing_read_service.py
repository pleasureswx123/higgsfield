"""制作任务只投影平台费用，不透传采购、账号及原始供应商证据。"""

from decimal import Decimal, localcontext
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from module_higgsfield.dao.billing_dao import BillingDao


class TaskBillingReadService:
    @staticmethod
    async def read(db, job, allowed):
        if 'project:usage:read' not in allowed:
            return {'billingVisibility': 'hidden'}
        scope, _ = await BillingDao.price(db, job.platform_price_version_id)
        if scope is None or scope[1].purpose != 'platform':
            return {'billingVisibility': 'unavailable'}
        currency = scope[1].currency
        facts = await BudgetReservationDao.billing_facts(db, job.job_id, 'platform')
        states = [event.state if event else '0' for _, event in facts]
        state = (
            'disputed'
            if '3' in states
            else 'pending'
            if not states or '0' in states
            else 'confirmed'
            if all(value == '2' for value in states)
            else 'calculated'
        )
        amount = None
        if facts and all(
            event is not None and event.amount is not None and event.currency == currency for _, event in facts
        ):
            with localcontext() as context:
                context.prec = 100
                total = Decimal(0)
                for _, event in facts:
                    total += event.amount + await BillingDao.adjustment_total(db, event.event_id)
                amount = format(total, '.10f')
        quantities = []
        for subject_id, event in facts:
            usage = await BillingDao.adopted_usage(db, event.usage_record_id) if event else None
            # 无物理外键，读取时同样验证证据归属；异常引用不得暴露其他对象用量。
            if event and event.usage_record_id is not None and (
                usage is None or usage.subject_id != subject_id
            ):
                return {'billingVisibility': 'unavailable'}
            if usage is None:
                continue
            values = {}
            for public, internal in (
                ('inputTokens', 'input_tokens'),
                ('outputTokens', 'output_tokens'),
                ('videoTokens', 'video_tokens'),
                ('imageCount', 'image_count'),
                ('outputSeconds', 'output_seconds'),
                ('referenceSeconds', 'reference_seconds'),
            ):
                value = getattr(usage, internal)
                values[public] = None if value is None else value if public == 'imageCount' else str(value)
            quantities.append({'subjectId': str(subject_id), **values})
        return {
            'billingVisibility': 'visible',
            'billing': {
                'platform': {'amount': amount, 'currency': currency, 'state': state},
                'usage': {'subjects': quantities},
            },
        }

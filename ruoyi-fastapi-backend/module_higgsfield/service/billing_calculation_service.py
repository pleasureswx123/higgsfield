"""按任务固定价格落库首次计价，后续修订不覆盖原始费用。"""

from decimal import Decimal

from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.entity.do.billing_do import HfBillingEvent, HfBillingLineItem
from module_higgsfield.service.price_calculation_service import CalculationItem, PriceCalculationService


class BillingCalculationService:
    fields = {
        'inputTokens': 'input_tokens',
        'outputTokens': 'output_tokens',
        'videoTokens': 'video_tokens',
        'imageCount': 'image_count',
        'outputSeconds': 'output_seconds',
        'referenceSeconds': 'reference_seconds',
    }

    @classmethod
    async def calculate(cls, db, *, job, subject_id, purpose, now, worker):
        """内部事务组件：调用方持有任务锁，负责聚合版本、事件及提交回滚。"""
        if purpose not in {'platform', 'procurement'}:
            raise ValueError('无效计价口径')
        subject = await BillingDao.subject(db, subject_id)
        if subject is None or subject.job_id != job.job_id or subject.subject_kind != 'generation':
            raise ValueError('计费对象不属于当前生成任务')
        version_id = getattr(job, f'{purpose}_price_version_id')
        if version_id is None:
            # 未知采购价格不能使用平台价格代替，也不能创建零价结果。
            return None, False
        scope, rules = await BillingDao.price(db, version_id)
        if scope is None:
            raise ValueError('固定价格版本不存在')
        version, book = scope
        if (
            version.status != '1'
            or book.purpose != purpose
            or book.model_variant_id != job.model_variant_id
            or (purpose == 'procurement' and book.account_id != subject.account_id)
            or (purpose == 'platform' and book.account_id is not None)
        ):
            raise ValueError('固定价格版本与任务或账号不一致')
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        event = await BillingDao.event(db, subject_id, purpose)
        created = event is None
        if created:
            event = await BillingDao.add(
                db,
                HfBillingEvent,
                dict(
                    subject_id=subject_id,
                    purpose=purpose,
                    price_version_id=version_id,
                    currency=book.currency,
                    **audit,
                ),
            )
        elif event.price_version_id != version_id or event.currency != book.currency:
            raise ValueError('既有计价事件固定价格不一致')
        evidence = await BillingDao.evidence(db, subject_id)
        if len(evidence) > 1:
            # 尚无供应商修订裁定证据，不以最后到达的记录重算原始金额。
            if event.state == '3':
                return event, created
            event.state = '3'
        elif event.amount is not None or event.state == '3' or not evidence:
            return event, created
        else:
            usage = evidence[0]
            items = [
                CalculationItem(
                    id=row.item_id,
                    item_code=row.item_code,
                    unit=row.unit,
                    unit_quantity=format(row.unit_quantity, 'f'),
                    unit_price=format(row.unit_price, 'f'),
                    quantity_from=format(row.quantity_from, 'f'),
                    quantity_to=None if row.quantity_to is None else format(row.quantity_to, 'f'),
                    formula_template=row.formula_template,
                    free_reason=row.free_reason,
                )
                for row in rules
            ]
            if not items or any(item.item_code not in PriceCalculationService.sources for item in items):
                raise ValueError('固定价格缺少受支持的计费分项')
            required = {PriceCalculationService.sources[item.item_code][0] for item in items}
            if any(getattr(usage, cls.fields[name]) is None for name in required):
                return event, created
            quantities = {
                name: (
                    getattr(usage, cls.fields[name])
                    if name == 'imageCount'
                    else str(getattr(usage, cls.fields[name]))
                    if name.endswith('Tokens')
                    else format(getattr(usage, cls.fields[name]), 'f')
                )
                for name in required
            }
            result = PriceCalculationService.calculate(
                items, quantities, calculation_scale=version.calculation_scale, rounding_mode=version.rounding_mode
            )
            for line in result['lines']:
                await BillingDao.add(
                    db,
                    HfBillingLineItem,
                    dict(
                        event_id=event.event_id,
                        rule_item_id=int(line['itemId']),
                        quantity=Decimal(line['quantity']),
                        unit_quantity=Decimal(line['unitQuantity']),
                        unit_price=Decimal(line['unitPrice']),
                        amount=Decimal(line['amount']),
                        calculation_snapshot={
                            **line,
                            'calculationScale': result['calculationScale'],
                            'roundingMode': result['roundingMode'],
                            'usageRecordId': str(usage.usage_id),
                            'priceVersionId': str(version_id),
                        },
                        **audit,
                    ),
                )
            event.amount = Decimal(result['total'])
            event.usage_record_id = usage.usage_id
            event.state = '1'
        if not created:
            event.revision += 1
        event.update_by, event.update_time = worker, now
        await db.flush()
        return event, True

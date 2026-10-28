"""按发送时采购快照与实际用量计价，不把初始未知修订当成第二笔消费。"""
from decimal import Decimal
from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.dao.usage_dao import UsageDao
from module_higgsfield.entity.do.billing_do import HfBillingEvent, HfBillingLineItem
from module_higgsfield.service.billing_calculation_service import BillingCalculationService
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.service.price_calculation_service import PriceCalculationService


class CredentialTestBillingService:
    @staticmethod
    async def calculate(db, test, call, *, now):
        """调用方持有测试与调用行锁，在同一事务提交用量、诊断及金额。"""
        pricing = call.request_metadata.get('procurementPricing', {})
        if pricing.get('state') != 'fixed':
            return None, False
        frozen = pricing['price']
        subject = await UsageDao.subject(db, call.call_id, 'test')
        if (subject is None or subject.cost_center_id != test.cost_center_id or subject.job_id is not None
                or subject.account_id != call.account_id or call.call_id != test.provider_call_id):
            raise ValueError('测试采购计价对象与原调用不一致')
        scope, rules = await BillingDao.price(db, int(frozen['priceVersionId']))
        if scope is None:
            raise ValueError('固定采购价格不存在')
        version, book = scope
        if (version.status != '1' or book.purpose != 'procurement' or book.account_id != subject.account_id
                or str(book.account_id) != frozen['accountId'] or book.currency != frozen['currency']
                or str(book.model_variant_id) != frozen['modelVariantId']
                or str(book.price_book_id) != frozen['priceBookId']
                or version.rounding_mode != frozen['roundingMode'] or version.calculation_scale != frozen['calculationScale']
                or [PriceVersionService.item(rule) for rule in rules] != frozen['items']):
            raise ValueError('采购价格内容与发送快照不一致')
        audit = dict(create_by='credential-test-worker', update_by='credential-test-worker', create_time=now, update_time=now)
        event = await BillingDao.event(db, subject.subject_id, 'procurement')
        created = event is None
        if created:
            event = await BillingDao.add(db, HfBillingEvent, dict(subject_id=subject.subject_id,
                purpose='procurement', price_version_id=version.price_version_id, currency=book.currency, **audit))
        elif event.price_version_id != version.price_version_id or event.currency != book.currency:
            raise ValueError('测试既有计价事件价格不一致')
        evidence = await BillingDao.evidence(db, subject.subject_id)
        # 初始占位只有未知且无原始计数，不能参与实际修订冲突判断或数量相加。
        evidence = [row for row in evidence if not (row.revision_no == 1 and row.completeness == 'unknown'
            and row.raw_usage == {} and all(getattr(row, name) is None for name in BillingCalculationService.fields.values()))]
        if len(evidence) > 1:
            if event.state == '3':
                return event, created
            event.state = '3'
        elif event.amount is not None or event.state == '3' or not evidence:
            return event, created
        else:
            usage = evidence[0]
            items = PriceVersionService.calculation_items(rules)
            if not items or any(item.item_code not in PriceCalculationService.sources for item in items):
                raise ValueError('采购价格分项不受支持')
            required = {PriceCalculationService.sources[item.item_code][0] for item in items}
            if any(getattr(usage, BillingCalculationService.fields[name]) is None for name in required):
                return event, created
            quantities = {name: (getattr(usage, BillingCalculationService.fields[name]) if name == 'imageCount'
                else str(getattr(usage, BillingCalculationService.fields[name]))) for name in required}
            result = PriceCalculationService.calculate(items, quantities, calculation_scale=version.calculation_scale,
                                                       rounding_mode=version.rounding_mode)
            for line in result['lines']:
                await BillingDao.add(db, HfBillingLineItem, dict(event_id=event.event_id,
                    rule_item_id=int(line['itemId']), quantity=Decimal(line['quantity']),
                    unit_quantity=Decimal(line['unitQuantity']), unit_price=Decimal(line['unitPrice']),
                    amount=Decimal(line['amount']), calculation_snapshot={**line,
                        'calculationScale': result['calculationScale'], 'roundingMode': result['roundingMode'],
                        'usageRecordId': str(usage.usage_id), 'priceVersionId': str(version.price_version_id)}, **audit))
            event.amount, event.usage_record_id, event.state = Decimal(result['total']), usage.usage_id, '1'
        if not created:
            event.revision += 1
        event.update_by, event.update_time = 'credential-test-worker', now
        await db.flush()
        return event, True

"""测试费用仅在采购读取的全部管理范围内投影，未知保持空值。"""
import re
from decimal import localcontext
from exceptions.exception import PermissionException
from module_higgsfield.dao.credential_test_cost_dao import CredentialTestCostDao
from module_higgsfield.service.admin_scope_service import AdminScopeService


class CredentialTestCostService:
    @staticmethod
    async def attach(db, user, records):
        hidden = [{key: value for key, value in record.items() if key != 'cost'} | {'costVisibility': 'hidden'}
                  for record in records]
        try:
            await AdminScopeService.global_access(db, user, 'billing:read')
        except PermissionException:
            return hidden
        facts = await CredentialTestCostDao.for_tests(db, [int(record['id']) for record in records])
        costs = {}
        for row in facts:
            cost = {'purpose': 'procurement', 'state': 'unknown', 'currency': None,
                    'amount': None, 'effectiveAmount': None, 'eventId': None}
            if row['call_id'] is None:
                cost['state'] = 'not_started'
            elif row['event_id'] is not None:
                cost.update(state=('pending', 'calculated', 'confirmed', 'disputed')[int(row['state'])],
                            currency=row['currency'], eventId=str(row['event_id']))
                if row['amount'] is not None:
                    with localcontext() as context:
                        context.prec = 100
                        cost['amount'] = format(row['amount'], '.10f')
                        cost['effectiveAmount'] = format(row['amount'] + row['adjustment_total'], '.10f')
            else:
                pricing = (row['request_metadata'] or {}).get('procurementPricing', {})
                if pricing.get('state') in {'fixed', 'unpriced'}:
                    cost['state'] = 'pending' if pricing['state'] == 'fixed' else 'unpriced'
                    currency = pricing.get('price', {}).get('currency') if pricing['state'] == 'fixed' else pricing.get('currency')
                    cost['currency'] = currency if isinstance(currency, str) and re.fullmatch('[A-Z]{3}', currency) else None
            costs[str(row['test_id'])] = cost
        return [record | {'costVisibility': 'visible', 'cost': costs[record['id']]} for record in records]

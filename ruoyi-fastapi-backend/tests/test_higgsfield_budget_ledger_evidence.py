"""预算账本展示证据白名单、大ID与十进制精度。"""
import unittest
from types import SimpleNamespace
from datetime import datetime, UTC
from decimal import Decimal
from module_higgsfield.service.budget_period_service import BudgetPeriodService


class LedgerEvidenceTests(unittest.TestCase):
    def row(self, **changes):
        return SimpleNamespace(**(dict(entry_id=9007199254740993, entry_type='adjust', business_event_key='adjust:1',
            reserved_delta=Decimal(0), consumed_delta=Decimal('-0.0000000001'), limit_delta=Decimal(0),
            reservation_id=1, billing_event_id=2, adjustment_id=9007199254740994,
            exchange_rate_version_id=9007199254740995, reason='核对差额', create_time=datetime.now(UTC),
            conversion_snapshot={'sourceAmount': '0.0000000002', 'rate': '3.000000000000',
                'direction': 'divide', 'convertedDelta': '-0.0000000001', 'internalSecret': '不得公开'}) | changes))

    def test_precision_identity_and_whitelist(self):
        result = BudgetPeriodService.ledger(self.row())
        self.assertEqual(result['adjustmentId'], '9007199254740994')
        self.assertEqual(result['exchangeRateVersionId'], '9007199254740995')
        self.assertEqual(result['consumedDelta'], '-0.0000000001')
        self.assertEqual(result['conversion']['sourceAmount'], '0.0000000002')
        self.assertNotIn('internalSecret', result['conversion'])

    def test_same_currency_does_not_invent_conversion(self):
        result = BudgetPeriodService.ledger(self.row(exchange_rate_version_id=None,
            reservation_id=None, adjustment_id=None, billing_event_id=None, conversion_snapshot={}))
        self.assertIsNone(result['conversion'])
        self.assertIsNone(result['exchangeRateVersionId'])
        self.assertIsNone(result['billingEventId'])

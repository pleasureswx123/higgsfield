"""费用互斥分桶、跨币种隔离及用量精度。"""

from dataclasses import replace
from decimal import Decimal
import unittest
from module_higgsfield.service.usage_summary_calculation_service import (
    UsageSummaryCalculationService as Summary,
    UsageSummaryFact,
)


class UsageSummaryCalculationTests(unittest.TestCase):
    def fact(self, **values):
        return UsageSummaryFact(
            **(
                dict(
                    event_id=1,
                    subject_id=1,
                    group_key='1',
                    display_name='项目一',
                    purpose='platform',
                    currency='CNY',
                    state='1',
                    amount=Decimal('12.393'),
                    input_tokens=9007199254740993,
                    usage_completeness='available',
                )
                | values
            )
        )

    def test_states_are_mutually_exclusive_and_adjustments_are_included(self):
        result = Summary.summarize(
            [
                self.fact(),
                self.fact(event_id=2, subject_id=2, state='2', amount=Decimal('10'), adjustment_total=Decimal('-3')),
                self.fact(event_id=3, subject_id=3, state='3', amount=Decimal('2')),
                self.fact(
                    event_id=4, subject_id=4, state='0', amount=None, input_tokens=None, usage_completeness='unknown'
                ),
            ],
            purpose='platform',
        )[0]
        self.assertEqual(result['calculatedAmount'], '12.3930000000')
        self.assertEqual(result['confirmedAmount'], '7.0000000000')
        self.assertEqual(result['disputedAmount'], '2.0000000000')
        self.assertEqual(result['totalKnownAmount'], '21.3930000000')
        self.assertEqual(result['unknownCount'], '1')
        self.assertEqual(result['inputTokens'], str(9007199254740993 * 3))
        self.assertEqual(result['usageCompleteness'], 'partial')

    def test_currencies_stay_separate_and_zero_is_known(self):
        rows = Summary.summarize(
            [
                self.fact(amount=Decimal(0), input_tokens=0),
                self.fact(
                    event_id=2,
                    subject_id=2,
                    currency='USD',
                    amount=None,
                    input_tokens=None,
                    usage_completeness='unknown',
                ),
            ],
            purpose='platform',
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['unknownCount'], '0')
        self.assertEqual(rows[0]['usageCompleteness'], 'available')
        self.assertEqual(rows[1]['unknownCount'], '1')
        self.assertEqual(rows[1]['usageCompleteness'], 'unknown')

    def test_duplicate_and_invalid_evidence_cannot_inflate_report(self):
        fact = self.fact()
        for facts in (
            [fact, fact],
            [fact, replace(fact, event_id=2)],
            [replace(fact, purpose='procurement')],
            [replace(fact, amount=Decimal('NaN'))],
            [replace(fact, amount=0.1)],
            [replace(fact, input_tokens=True)],
            [replace(fact, adjustment_total=Decimal('-100'))],
        ):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                Summary.summarize(facts, purpose='platform')

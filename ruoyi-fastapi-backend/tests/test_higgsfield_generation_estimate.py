"""预算上界预估不接受未知值替零，保留双口径价格与策略证据。"""

import unittest
from copy import deepcopy

from pydantic import ValidationError

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.generation_estimate_vo import GenerationEstimatePolicy
from module_higgsfield.service.generation_estimate_service import GenerationEstimateService
from tests.test_higgsfield_model_capabilities import capability


class GenerationEstimateTests(unittest.TestCase):
    def policy(self, **usage) -> GenerationEstimatePolicy:
        return GenerationEstimatePolicy(
            strategy='fixed_usage_upper_bound',
            evidenceRef='review/estimate/1',
            scopeStatement='仅测试策略；覆盖本能力全部合法请求',
            upperBounds=usage,
        )

    def prices(self) -> dict:
        item = {
            'id': '1',
            'itemCode': 'video_tokens',
            'unit': 'token',
            'unitQuantity': '1000000',
            'unitPrice': '70',
            'quantityFrom': '0',
            'quantityTo': None,
            'formulaTemplate': 'linear',
            'freeReason': None,
        }
        return {
            name: {
                'currency': currency,
                'priceVersionId': identity,
                'calculationScale': 10,
                'roundingMode': 'half_up',
                'items': [dict(item, unitPrice=price)],
            }
            for name, currency, identity, price in [('platform', 'CNY', '1', '70'), ('procurement', 'USD', '2', '10')]
        }

    def test_fixed_upper_bound_and_separate_price_evidence(self) -> None:
        cap = capability().model_copy(update={'estimate_policy': self.policy(videoTokens='1000001')})
        prices = self.prices()
        before = deepcopy(prices)
        result = GenerationEstimateService.calculate(
            cap, model_version_id='9', input_snapshot={'parameters': {'n': 1}}, prices=prices
        )
        self.assertEqual(result['estimates']['platform']['total'], '70.0000700000')
        self.assertEqual(result['estimates']['procurement']['total'], '10.0000100000')
        self.assertEqual(result['policy']['evidenceRef'], 'review/estimate/1')
        self.assertEqual(result['modelVersionId'], '9')
        self.assertEqual(prices, before)
        changed = GenerationEstimateService.calculate(
            cap, model_version_id='9', input_snapshot={'parameters': {'n': 2}}, prices=prices
        )
        self.assertNotEqual(result['inputHash'], changed['inputHash'])

    def test_unknown_not_zero_and_explicit_zero_supported(self) -> None:
        cap = capability()
        with self.assertRaises(ServiceWarning):
            GenerationEstimateService.calculate(cap, model_version_id='9', input_snapshot={}, prices=self.prices())
        cap = cap.model_copy(update={'estimate_policy': self.policy(outputTokens='100')})
        with self.assertRaises(ValueError):
            GenerationEstimateService.calculate(cap, model_version_id='9', input_snapshot={}, prices=self.prices())
        cap = cap.model_copy(update={'estimate_policy': self.policy(videoTokens='0')})
        result = GenerationEstimateService.calculate(cap, model_version_id='9', input_snapshot={}, prices=self.prices())
        self.assertEqual(result['estimates']['platform']['total'], '0.0000000000')

    def test_policy_requires_exact_bounded_values(self) -> None:
        for values in (
            {},
            {'videoTokens': None},
            {'videoTokens': 1},
            {'videoTokens': '1.2'},
            {'videoTokens': '9223372036854775808'},
            {'outputSeconds': '1e3'},
            {'imageCount': True},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.policy(**values)

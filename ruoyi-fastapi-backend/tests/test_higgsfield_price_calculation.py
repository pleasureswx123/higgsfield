"""设计算例、精度边界及累计阶梯的独立验证。"""

from decimal import Decimal, localcontext
from unittest import TestCase

from module_higgsfield.service.price_calculation_service import CalculationItem, PriceCalculationService


def item(identity=1, code='video_tokens', price='70', base='1000000', start='0', end=None, template='linear'):
    unit = PriceCalculationService.sources[code][1]
    return CalculationItem(
        identity, code, unit, base, price, start, end, template, '报价免费区间' if price == '0' else None
    )


def calculate(items, usage, scale=10):
    return PriceCalculationService.calculate(items, usage, calculation_scale=scale, rounding_mode='half_up')


class PriceCalculationTests(TestCase):
    def test_documented_token_examples(self):
        self.assertEqual(calculate([item()], {'videoTokens': '108000'})['total'], '7.5600000000')
        self.assertEqual(calculate([item(price='51')], {'videoTokens': '243000'})['total'], '12.3930000000')
        result = calculate(
            [item(code='input', price='0.27'), item(2, 'output', '30')],
            {'inputTokens': '10000', 'outputTokens': '2000'},
        )
        self.assertEqual(result['total'], '0.0627000000')
        result = calculate(
            [item(code='input', price='5'), item(2, 'output', '30')],
            {'inputTokens': '2000', 'outputTokens': '4000', 'imageCount': 2},
        )
        self.assertEqual(result['total'], '0.1300000000')

    def test_cumulative_free_tier(self):
        items = [
            item(1, 'input_images', '0', '1', '0', '5', 'tiered'),
            item(2, 'input_images', '0.04', '1', '5', None, 'tiered'),
            item(3, 'output_seconds', '0.13', '1'),
            item(4, 'reference_seconds', '0.13', '1'),
        ]
        self.assertEqual(
            calculate(items, {'imageCount': 7, 'outputSeconds': '10', 'referenceSeconds': '2'})['total'], '1.6400000000'
        )
        self.assertEqual(calculate(items[:2], {'imageCount': 5})['total'], '0.0000000000')

    def test_rounding_conservation_and_stable_id_tie_break(self):
        items = [item(8, 'input', '1', '3'), item(3, 'output', '1', '3')]
        with localcontext() as context:
            context.prec = 6
            result = calculate(items, {'inputTokens': '1', 'outputTokens': '1'}, 2)
        self.assertEqual(result['total'], '0.67')
        self.assertEqual([line['amount'] for line in result['lines']], ['0.34', '0.33'])
        self.assertEqual(sum(Decimal(line['amount']) for line in result['lines']), Decimal(result['total']))
        self.assertEqual(result, calculate(items[::-1], {'inputTokens': '1', 'outputTokens': '1'}, 2))

    def test_missing_invalid_usage_and_unsupported_templates(self):
        for usage in (
            {},
            {'videoTokens': None},
            {'videoTokens': 1},
            {'videoTokens': '1.0'},
            {'videoTokens': '1e3'},
            {'videoTokens': '-1'},
            {'videoTokens': '9223372036854775808'},
            {'videoTokens': '0', 'cacheTokens': '1'},
        ):
            with self.subTest(usage=usage), self.assertRaises(ValueError):
                calculate([item()], usage)
        for rule in (
            item(base='0'),
            item(price='0.00000000001'),
            item(template='eval'),
            item(start='1'),
            item(end='10'),
            item(price='99999999999999'),
        ):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                calculate([rule], {'videoTokens': '9223372036854775807'})
        self.assertEqual(calculate([item()], {'videoTokens': '0'})['total'], '0.0000000000')

    def test_tier_gap_overlap_and_duplicate_rejected(self):
        for start in ('4', '6'):
            with self.assertRaises(ValueError):
                calculate(
                    [item(end='5', template='tiered'), item(2, start=start, template='tiered')], {'videoTokens': '7'}
                )
        with self.assertRaises(ValueError):
            calculate([item(), item()], {'videoTokens': '7'})

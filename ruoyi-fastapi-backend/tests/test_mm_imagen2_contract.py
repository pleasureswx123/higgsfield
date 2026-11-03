"""不调用供应商，验证尺寸映射、压缩容量及真实Token价格公式。"""

import gzip
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import brotli

from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.image_size_service import ImageSizeService
from module_higgsfield.service.price_calculation_service import CalculationItem, PriceCalculationService
from module_higgsfield.service.provider_decode_service import ProviderDecodeService


class MmImagen2ContractTests(unittest.TestCase):
    def test_mapping_table(self):
        expected = {
            '1:1': ('1024x1024', '2048x2048', '3840x3840'),
            '3:2': ('1024x688', '2048x1360', '3840x2560'),
            '2:3': ('688x1024', '1360x2048', '2560x3840'),
            '16:9': ('1024x576', '2048x1152', '3840x2160'),
            '9:16': ('576x1024', '1152x2048', '2160x3840'),
            '4:3': ('1024x768', '2048x1536', '3840x2880'),
            '3:4': ('768x1024', '1536x2048', '2880x3840'),
            '21:9': ('1024x432', '2048x880', '3840x1648'),
        }
        for ratio, sizes in expected.items():
            for resolution, size in zip(('1K', '2K', '4K'), sizes):
                self.assertEqual(ImageSizeService.size(ratio, resolution), size)
        self.assertEqual(ImageSizeService.size('Auto', '2K'), 'auto')
        with self.assertRaises(ValueError):
            ImageSizeService.parameters({'aspect_ratio': '16:9', 'resolution': '2K', 'size': '1024x1024'})

    def test_compressed_response_limits_and_truncation(self):
        original = b'{"images":[]}' * 10000
        for encoding, compress in (('gzip', gzip.compress), ('br', brotli.compress)):
            wire = compress(original)
            decoder = ProviderDecodeService(encoding, len(original))
            decoded = b''.join(decoder.feed(wire[i:i + 17]) for i in range(0, len(wire), 17))
            decoder.finish()
            self.assertEqual(decoded, original)
            with self.assertRaises(ValueError):
                ProviderDecodeService(encoding, 1024).feed(wire)
            decoder = ProviderDecodeService(encoding, len(original))
            decoder.feed(wire[:-1])
            with self.assertRaises(ValueError):
                decoder.finish()

    def test_actual_token_price(self):
        items = [CalculationItem(id=index, item_code=code, unit='token', unit_quantity='1000000',
            unit_price=price, quantity_from='0', quantity_to=None, formula_template='linear')
            for index, (code, price) in enumerate((('input', '5'), ('output', '30')), 1)]
        result = PriceCalculationService.calculate(items, {'inputTokens': '120', 'outputTokens': '4096'},
            calculation_scale=10, rounding_mode='half_up')
        self.assertEqual(result['total'], '0.1234800000')


class ActualUsageAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_accept_without_quote_or_budget_keeps_destination_and_prices(self):
        """不提供估价凭据或预算配置，受理仍固定原目录和两套价格。"""
        module = 'module_higgsfield.service.generation_accept_service.'
        db = SimpleNamespace(rollback=AsyncMock(), commit=AsyncMock())
        user = SimpleNamespace(user=SimpleNamespace(user_id=7, user_name='tester', dept_id=1, dept=None))
        payload = SimpleNamespace(project_id='2', kind='image', model_dump=lambda **kwargs: {'projectId': '2'})
        prepared = {
            'acceptedAt': None, 'modelVersionId': '3', 'modelVariantId': '4',
            'inputSnapshot': {'folderId': '9', 'compiled': {'media': []}},
            'route': {'credentialVersionId': '5'},
            'prices': {'platform': {'priceVersionId': '6'}, 'procurement': {'priceVersionId': '8'}},
            'estimate': {'mode': 'actual_usage', 'estimates': {}},
        }
        job = SimpleNamespace(job_id=10, input_snapshot={})
        with (
            patch(module + 'WriteService.lock', new_callable=AsyncMock),
            patch(module + 'WorkspaceService.authorize', new_callable=AsyncMock),
            patch(module + 'GenerationAcceptDao.existing', new=AsyncMock(return_value=None)),
            patch(module + 'WriteService.replay', new=AsyncMock(return_value=None)),
            patch(module + 'GenerationPreparationService.prepare', new=AsyncMock(return_value=prepared)),
            patch(module + 'WriteService.audit', return_value={}),
            patch(module + 'GenerationAcceptDao.create', new=AsyncMock(return_value=job)) as create,
            patch(module + 'JobEventDao.state', new_callable=AsyncMock),
            patch(module + 'WriteService.finish', new=AsyncMock(return_value=({'id': '10'}, False))),
            patch('module_higgsfield.service.budget_reservation_service.BudgetReservationService.reserve',
                  new=AsyncMock(side_effect=AssertionError('新任务不得预占预算'))) as reserve,
        ):
            await GenerationAcceptService.accept(db, user, payload, 'unique-key',
                currencies={'platform': 'USD', 'procurement': 'USD'}, missing_budget_policy='allow')
        reserve.assert_not_awaited()
        self.assertEqual(job.input_snapshot['billingMode'], 'actual_usage')
        self.assertEqual(job.input_snapshot['folderId'], '9')
        self.assertEqual(job.input_snapshot['budgetReservations'], [])
        self.assertEqual(create.await_args.args[1]['procurement_price_version_id'], 8)
        self.assertEqual(create.await_args.args[1]['platform_price_version_id'], 6)
        db.rollback.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()

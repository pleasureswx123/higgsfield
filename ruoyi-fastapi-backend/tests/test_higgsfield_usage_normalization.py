"""实际用量未知、部分、零值和计费语义，证据摘要不受返回字段顺序影响。"""

import unittest

from module_higgsfield.service.usage_normalization_service import UsageNormalizationService


class UsageNormalizationTests(unittest.TestCase):
    def test_image_request_usage_not_multiplied_and_zero_is_available(self) -> None:
        fact = UsageNormalizationService.image({'input_tokens': 0, 'output_tokens': 12, 'image_count': 8})
        self.assertEqual((fact.input_tokens, fact.output_tokens, fact.completeness), (0, 12, 'available'))
        same = UsageNormalizationService.image({'output_tokens': 12, 'input_tokens': 0})
        self.assertEqual(fact.payload_hash, same.payload_hash)
        self.assertNotIn('image_count', fact.raw_usage)

    def test_missing_partial_invalid_values_are_not_zero(self) -> None:
        self.assertEqual(UsageNormalizationService.image(None).completeness, 'unknown')
        for value in (True, -1, 0.5, '12', 9223372036854775808, float('nan')):
            fact = UsageNormalizationService.image({'input_tokens': 4, 'output_tokens': value})
            self.assertEqual(fact.completeness, 'partial')
            self.assertIsNone(fact.output_tokens)
            self.assertIn('OUTPUT_TOKENS_INVALID', fact.issues)
        fact = UsageNormalizationService.image(
            {'input_tokens': 'https://secret.example/key', 'output_tokens': {'token': 'secret'}}
        )
        self.assertNotIn('secret', fact.model_dump_json())

    def test_video_completion_is_only_video_tokens(self) -> None:
        fact = UsageNormalizationService.video({'completion_tokens': 123, 'total_tokens': 456})
        self.assertEqual(fact.video_tokens, 123)
        self.assertIsNone(fact.input_tokens)
        self.assertIsNone(fact.output_tokens)
        self.assertEqual(fact.completeness, 'available')
        self.assertEqual(UsageNormalizationService.video({'total_tokens': 456}).completeness, 'unknown')
        changed = UsageNormalizationService.video({'completion_tokens': 124})
        self.assertNotEqual(changed.payload_hash, fact.payload_hash)

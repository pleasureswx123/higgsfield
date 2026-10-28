"""图片嵌套契约、用量来源、资源限制与单图错误隔离。"""

import base64
import json
import unittest

from module_higgsfield.service.image_response_service import ImageResponseService


class ImageResponseTests(unittest.TestCase):
    @staticmethod
    def body(inner: dict) -> dict:
        return {
            'id': 'image-response-1',
            'choices': [{'message': {'content': json.dumps(inner)}}],
            'usage': {'input_tokens': 0, 'output_tokens': 0},
        }

    def test_inner_usage_and_private_image_bytes(self) -> None:
        result = ImageResponseService.parse(
            200,
            self.body(
                {
                    'images': [
                        {'b64_json': base64.b64encode(b'private-image-data').decode(), 'revised_prompt': '晨光'}
                    ],
                    'usage': {'input_tokens': 123, 'output_tokens': 456},
                    'output_format': 'png',
                    'size': '1024x1024',
                }
            ),
            max_bytes=1000,
            expected_count=1,
        )
        self.assertEqual(result.usage, {'input_tokens': '123', 'output_tokens': '456'})
        self.assertEqual(result.images[0].data.get_secret_value(), b'private-image-data')
        self.assertNotIn('private-image-data', repr(result))
        self.assertNotIn('data', result.model_dump()['images'][0])
        self.assertEqual(result.issues, [])

    def test_bad_image_does_not_renumber_good_images(self) -> None:
        result = ImageResponseService.parse(
            200,
            self.body(
                {
                    'images': [{'b64_json': '%%%invalid'}, {'b64_json': 'YWJj'}],
                    'usage': {'input_tokens': True},
                }
            ),
            max_bytes=100,
            expected_count=3,
        )
        self.assertEqual([image.ordinal for image in result.images], [1])
        self.assertEqual(result.rejected_ordinals, [0])
        self.assertEqual(result.usage, {})
        self.assertIn('OUTPUT_COUNT_MISMATCH', result.issues)
        self.assertIn('USAGE_OUTPUT_TOKENS_MISSING_OR_INVALID', result.issues)

    def test_total_decode_limit(self) -> None:
        result = ImageResponseService.parse(
            200,
            self.body(
                {
                    'images': [{'b64_json': 'YWJj'}, {'b64_json': 'ZGVm'}],
                }
            ),
            max_bytes=5,
            expected_count=2,
        )
        self.assertEqual([image.ordinal for image in result.images], [0])
        self.assertEqual(result.rejected_ordinals, [1])

    def test_contract_changes_and_ambiguous_json_are_rejected(self) -> None:
        for content in ({'images': []}, '{"images":[],"images":[]}', '{"images":[{}],"value":NaN}', '{"images":[]}'):
            body = {'choices': [{'message': {'content': content}}]}
            with self.subTest(content=content), self.assertRaises(ValueError):
                ImageResponseService.parse(200, body, max_bytes=1000, expected_count=1)

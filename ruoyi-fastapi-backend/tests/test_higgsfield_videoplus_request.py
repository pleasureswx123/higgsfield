"""固定序号的引用文本、媒体数组及供应商参数映射验证。"""

import unittest

from pydantic import SecretStr

from module_higgsfield.service.videoplus_request_service import VideoPlusRequestService
from tests.test_higgsfield_model_capabilities import capability


class VideoPlusRequestTests(unittest.TestCase):
    def test_asset_reference_and_url_keep_original_order(self) -> None:
        snapshot = {
            'parameters': {'duration': 6},
            'compiled': {
                'compilerVersion': 1,
                'media': [
                    {'ordinal': 0, 'mediaType': 'image', 'mediaRole': 'reference_image'},
                    {'ordinal': 1, 'mediaType': 'image', 'mediaRole': 'reference_image'},
                ],
                'promptParagraphs': [[{'type': 'reference', 'ordinals': [0, 1]}]],
            },
        }
        urls = {0: SecretStr('https://example.com/room.png'), 1: SecretStr('asset://asset-20261023155807-t6lpb')}
        cap = capability()
        cap.reference_rules.roles['first_frame'].min_count = 0
        result = VideoPlusRequestService.video('mm-eva-sd-2.5', cap, snapshot, urls)
        content = result['messages'][0]['content']
        self.assertEqual(content[0]['text'], '图片 1、图片 2')
        self.assertEqual(content[1]['image_url']['url'], urls[0].get_secret_value())
        self.assertEqual(content[2]['image_url']['url'], urls[1].get_secret_value())
        for invalid in ('asset://wrong-id', 'asset://asset-valid/path', 'asset://asset-valid?key=value'):
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                VideoPlusRequestService.video('mm-eva-sd-2.5', cap, snapshot, {**urls, 1: SecretStr(invalid)})

    def test_mentions_use_fixed_order_and_audio_is_mapped(self) -> None:
        snapshot = {
            'parameters': {'duration': 6},
            'compiled': {
                'compilerVersion': 1,
                'media': [
                    {'ordinal': 0, 'mediaType': 'image', 'mediaRole': 'first_frame'},
                    {'ordinal': 1, 'mediaType': 'image', 'mediaRole': 'reference_image'},
                ],
                'promptParagraphs': [[{'type': 'text', 'text': '使用'}, {'type': 'reference', 'ordinals': [1, 0]}]],
            },
        }
        result = VideoPlusRequestService.video(
            'test-model',
            capability(),
            snapshot,
            {
                0: SecretStr('https://example.com/first'),
                1: SecretStr('https://example.com/reference'),
            },
        )
        self.assertEqual(result['generate_audio'], False)
        self.assertNotIn('audio', result)
        content = result['messages'][0]['content']
        self.assertEqual(content[0], {'type': 'text', 'text': '使用图片 2、图片 1'})
        self.assertEqual(content[1]['role'], 'first_frame')
        self.assertEqual(content[2]['image_url']['url'], 'https://example.com/reference')
        self.assertEqual(snapshot['parameters'], {'duration': 6})
        with self.assertRaises(ValueError):
            VideoPlusRequestService.video('test-model', capability(), snapshot)

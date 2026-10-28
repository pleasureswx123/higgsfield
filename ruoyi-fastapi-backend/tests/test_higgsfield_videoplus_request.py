"""固定序号的引用文本、媒体数组及供应商参数映射验证。"""

import unittest

from pydantic import SecretStr

from module_higgsfield.service.videoplus_request_service import VideoPlusRequestService
from tests.test_higgsfield_model_capabilities import capability


class VideoPlusRequestTests(unittest.TestCase):
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

"""图片请求固定顺序、契约参数边界及原始快照不变性。"""

import copy
import unittest

from pydantic import SecretStr, ValidationError

from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.image_request_service import ImageRequestService


def capability() -> ModelCapabilities:
    return ModelCapabilities.model_validate(
        {
            'parametersSchema': {
                'properties': {
                    'n': {'type': 'integer'},
                    'size': {'type': 'string'},
                    'quality': {'type': 'string'},
                    'output_format': {'type': 'string'},
                    'output_compression': {'type': 'integer'},
                    'moderation': {'type': 'string'},
                }
            },
            'defaultParameters': {'n': 1, 'size': 'auto', 'output_format': 'png'},
            'referenceRules': {'maxTotal': 16, 'roles': {'reference_image': {'mediaTypes': ['image'], 'maxCount': 16}}},
        }
    )


def snapshot() -> dict:
    return {
        'parameters': {},
        'compiled': {
            'compilerVersion': 1,
            'media': [],
            'promptParagraphs': [[{'type': 'text', 'text': '晨光中的摄影棚'}]],
        },
    }


class ImageRequestTests(unittest.TestCase):
    def test_text_defaults_and_png_compression_not_sent(self) -> None:
        source = snapshot()
        source['parameters'] = {'n': 2, 'output_compression': 50}
        before = copy.deepcopy(source)
        result = ImageRequestService.compile('mm-imagen2', capability(), source)
        self.assertEqual(result['messages'], [{'role': 'user', 'content': '晨光中的摄影棚'}])
        self.assertEqual(result['n'], 2)
        self.assertNotIn('output_compression', result)
        self.assertEqual(source, before)
        source['parameters']['output_format'] = 'jpeg'
        self.assertEqual(ImageRequestService.compile('mm-imagen2', capability(), source)['output_compression'], 50)

    def test_fixed_media_order_and_mentions(self) -> None:
        source = snapshot()
        source['compiled']['media'] = [
            {'ordinal': i, 'mediaType': 'image', 'mediaRole': 'reference_image'} for i in range(2)
        ]
        source['compiled']['promptParagraphs'][0].append({'type': 'reference', 'ordinals': [1, 0]})
        urls = {i: SecretStr(f'https://media.example/{i}') for i in range(2)}
        result = ImageRequestService.compile('mm-imagen2', capability(), source, urls)
        content = result['messages'][0]['content']
        self.assertEqual(content[0]['text'], '晨光中的摄影棚图片 2、图片 1')
        self.assertEqual(content[1], {'type': 'image_url', 'image_url': {'url': 'https://media.example/0'}})
        with self.assertRaises(ValueError):
            ImageRequestService.compile('mm-imagen2', capability(), source)
        source['compiled']['promptParagraphs'][0][-1]['ordinals'] = [False]
        with self.assertRaises(ValueError):
            ImageRequestService.compile('mm-imagen2', capability(), source, urls)

    def test_contract_limits_override_loose_capability(self) -> None:
        for parameters in (
            {'n': 11},
            {'size': '3841x1024'},
            {'size': '1025x1024'},
            {'size': '3840x1024'},
            {'quality': 'extreme'},
            {'moderation': 'low'},
            {'output_compression': 101},
        ):
            source = snapshot()
            source['parameters'] = parameters
            with self.subTest(parameters=parameters), self.assertRaises(ValidationError):
                ImageRequestService.compile('mm-imagen2', capability(), source)
        for size in ('auto', '3840x1280', '1024x1024'):
            source = snapshot()
            source['parameters'] = {'size': size}
            self.assertEqual(ImageRequestService.compile('mm-imagen2', capability(), source)['size'], size)

    def test_prompt_length_and_empty_prompt_rejected(self) -> None:
        for prompt in (' ', '图' * 32001):
            source = snapshot()
            source['compiled']['promptParagraphs'][0][0]['text'] = prompt
            with self.assertRaises(ValueError):
                ImageRequestService.compile('mm-imagen2', capability(), source)

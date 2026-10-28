"""按已留存的mm-imagen2契约解析一次内层JSON及有界Base64。"""

import base64
import binascii
import json
import re

from pydantic import ValidationError

from module_higgsfield.entity.vo.image_provider_fact_vo import ImageProviderFact, ProviderImage
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService
from module_higgsfield.service.videoplus_response_service import IDENTIFIER, MAX_TOKEN_COUNT, unique_object

MAX_IMAGES, MAX_PROMPT = 10, 32000
HTTP_OK, HTTP_REDIRECT = 200, 300


def reject_constant(value: str) -> None:
    raise ValueError('图片响应包含非有限JSON数字')


class ImageResponseService:
    @staticmethod
    def parse(http_status: int, body: object, *, max_bytes: int, expected_count: int) -> ImageProviderFact:
        """总解码字节上限由部署配置明确给出；实际媒体格式由后续存储校验。"""
        if (
            type(max_bytes) is not int
            or max_bytes <= 0
            or type(expected_count) is not int
            or not 1 <= expected_count <= MAX_IMAGES
        ):
            raise ValueError('图片解析容量或数量配置无效')
        if not HTTP_OK <= http_status < HTTP_REDIRECT or not isinstance(body, dict):
            raise ValueError('图片响应未证明成功')
        fact = ImageProviderFact()
        try:
            fact.response_id = IDENTIFIER.validate_python(body.get('id'))
        except ValidationError:
            fact.issues.append('RESPONSE_ID_MISSING_OR_INVALID')
        inner = ImageResponseService._inner(body, max_bytes)
        if len(inner['images']) != expected_count:
            fact.issues.append('OUTPUT_COUNT_MISMATCH')
        ImageResponseService._images(inner, max_bytes, fact)
        ImageResponseService._metadata(inner, fact)
        return fact

    @staticmethod
    def _inner(body: dict, max_bytes: int) -> dict:
        try:
            choices = body['choices']
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            content = choices[0]['message']['content']
            # Base64膨胀上限之外仅预留有限的JSON、提示词和元数据空间。
            if not isinstance(content, str) or len(content) > 4 * ((max_bytes + 2) // 3) + 1_000_000:
                raise ValueError
            inner = json.loads(content, object_pairs_hook=unique_object, parse_constant=reject_constant)
            if (
                not isinstance(inner, dict)
                or not isinstance(inner.get('images'), list)
                or not 1 <= len(inner['images']) <= MAX_IMAGES
            ):
                raise ValueError
            if 'base_resp' in inner:
                base = inner['base_resp']
                if not isinstance(base, dict) or type(base.get('status_code')) is not int or base['status_code'] != 0:
                    raise ValueError
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            raise ValueError('图片响应内层契约无效') from None
        return inner

    @staticmethod
    def _images(inner: dict, max_bytes: int, fact: ImageProviderFact) -> None:
        remaining = max_bytes
        for ordinal, item in enumerate(inner['images']):
            try:
                encoded = item.get('b64_json') if isinstance(item, dict) else None
                if not isinstance(encoded, str) or not encoded or len(encoded) > 4 * ((remaining + 2) // 3):
                    raise ValueError
                data = base64.b64decode(encoded, validate=True)
                if not data or len(data) > remaining:
                    raise ValueError
                remaining -= len(data)
                prompt = item.get('revised_prompt')
                if prompt is not None and (not isinstance(prompt, str) or len(prompt) > MAX_PROMPT):
                    prompt = None
                    fact.issues.append('REVISED_PROMPT_INVALID')
                fact.images.append(ProviderImage(ordinal=ordinal, data=data, revised_prompt=prompt))
            except (ValueError, binascii.Error):  # noqa: PERF203 -- 单图失败不能丢弃同批其他图片
                fact.rejected_ordinals.append(ordinal)
        if fact.rejected_ordinals:
            fact.issues.append('IMAGE_DATA_INVALID_OR_TOO_LARGE')

    @staticmethod
    def _metadata(inner: dict, fact: ImageProviderFact) -> None:
        usage = inner.get('usage')
        fact.usage_fact = UsageNormalizationService.image(usage)
        for key in ('input_tokens', 'output_tokens'):
            value = usage.get(key) if isinstance(usage, dict) else None
            if type(value) is int and 0 <= value <= MAX_TOKEN_COUNT:
                fact.usage[key] = str(value)
            else:
                fact.issues.append('USAGE_' + key.upper() + '_MISSING_OR_INVALID')
        if inner.get('output_format') in ('png', 'jpeg', 'webp'):
            fact.declared_format = inner['output_format']
        elif 'output_format' in inner:
            fact.issues.append('DECLARED_FORMAT_INVALID')
        size = inner.get('size')
        if isinstance(size, str) and (size == 'auto' or re.fullmatch(r'[1-9][0-9]{0,4}x[1-9][0-9]{0,4}', size)):
            fact.declared_size = size
        elif 'size' in inner:
            fact.issues.append('DECLARED_SIZE_INVALID')

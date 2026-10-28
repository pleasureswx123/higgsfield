"""固定图片输入快照编译，不读取NAS或自行生成外部访问地址。"""

from pydantic import SecretStr

from module_higgsfield.entity.vo.image_request_vo import ImageRequestParameters
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.model_capability_service import ModelCapabilityService
from utils.output_source_util import validate_output_source

MAX_REFERENCES, MAX_PROMPT = 16, 32000


class ImageRequestService:
    @staticmethod
    def compile(
        gateway_alias: str,
        capabilities: ModelCapabilities,
        snapshot: dict,
        media_urls: dict[int, SecretStr] | None = None,
    ) -> dict:
        normalized = ModelCapabilityService.parameters(capabilities, snapshot['parameters'])
        parameters = ImageRequestParameters.model_validate(normalized).model_dump(exclude_unset=True, exclude_none=True)
        if parameters.get('output_format', 'png') == 'png':
            parameters.pop('output_compression', None)
        compiled = snapshot['compiled']
        if compiled.get('compilerVersion') != 1:
            raise ValueError('不支持的固定图片输入版本')
        ModelCapabilityService.references(capabilities, compiled)
        media, urls = compiled['media'], media_urls or {}
        if len(media) > MAX_REFERENCES or set(urls) != set(range(len(media))):
            raise ValueError('参考图数量超限或缺少固定序号的可访问地址')
        contents, labels = [], {}
        for ordinal, item in enumerate(media):
            if item['ordinal'] != ordinal or item['mediaType'] != 'image' or item['mediaRole'] != 'reference_image':
                raise ValueError('图片接口仅支持按固定序号排列的参考图')
            url = urls[ordinal].get_secret_value()
            validate_output_source(url)
            labels[ordinal] = f'图片 {ordinal + 1}'
            contents.append({'type': 'image_url', 'image_url': {'url': url}})
        prompt = ImageRequestService._prompt(compiled['promptParagraphs'], labels)
        content = [{'type': 'text', 'text': prompt}, *contents] if contents else prompt
        return {'model': gateway_alias, 'messages': [{'role': 'user', 'content': content}], **parameters}

    @staticmethod
    def _prompt(paragraphs: list, labels: dict[int, str]) -> str:
        result = []
        for paragraph in paragraphs:
            segments = []
            for node in paragraph:
                if node['type'] == 'text':
                    segments.append(node['text'])
                elif node['type'] == 'reference':
                    ordinals = node['ordinals']
                    if any(type(ordinal) is not int or ordinal not in labels for ordinal in ordinals):
                        raise ValueError('提示词引用未绑定的图片序号')
                    segments.append('、'.join(labels[ordinal] for ordinal in ordinals))
                else:
                    raise ValueError('不支持的提示词节点')
            result.append(''.join(segments))
        prompt = '\n'.join(result)
        if not prompt.strip() or len(prompt) > MAX_PROMPT:
            raise ValueError('图片提示词为空或超出契约长度')
        return prompt

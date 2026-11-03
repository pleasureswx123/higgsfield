"""将固定引用快照编译为VideoPlus请求，不生成外部媒体地址。"""

import re

from pydantic import SecretStr

from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.model_capability_service import ModelCapabilityService
from utils.output_source_util import validate_output_source

VIDEO_PARAMETERS = {
    'resolution',
    'duration',
    'ratio',
    'generate_audio',
    'bitrate_mode',
    'seed',
    'watermark',
    'execution_expires_after',
    'service_tier',
    'return_last_frame',
    'safety_identifier',
}
MEDIA_ROLES = {'image': {'first_frame', 'last_frame', 'reference_image', 'reference_person'}, 'video': {'reference_video'}, 'audio': {'reference_audio'}}
MEDIA_LABELS = {'image': '图片', 'video': '视频', 'audio': '音频'}


class VideoPlusRequestService:
    @staticmethod
    def video(
        gateway_alias: str,
        capabilities: ModelCapabilities,
        snapshot: dict,
        media_urls: dict[int, SecretStr] | None = None,
    ) -> dict:
        parameters = ModelCapabilityService.parameters(capabilities, snapshot['parameters'])
        # 平台能力中的audio开关对应网关generate_audio，禁止两个名称产生歧义。
        if 'audio' in parameters:
            if 'generate_audio' in parameters:
                raise ValueError('音频参数存在重复映射')
            parameters['generate_audio'] = parameters.pop('audio')
        if set(parameters) - VIDEO_PARAMETERS or parameters.get('service_tier', 'default') != 'default':
            raise ValueError('固定参数包含尚未开放的VideoPlus字段')
        compiled = snapshot['compiled']
        if compiled.get('compilerVersion') != 1:
            raise ValueError('不支持的固定输入编译版本')
        ModelCapabilityService.references(capabilities, compiled)
        urls = media_urls or {}
        media = compiled['media']
        if gateway_alias == 'mm-h3':
            roles = {item['mediaRole'] for item in media}
            if roles & {'first_frame', 'last_frame'} and roles & {'reference_image', 'reference_video', 'reference_audio', 'reference_person'}:
                raise ValueError('H3 首尾帧与参考素材模式不能混用')
            if not media and parameters.get('ratio') == 'adaptive':
                raise ValueError('H3 文生视频必须选择具体比例')
        if set(urls) != set(range(len(media))):
            raise ValueError('引用媒体尚未取得与固定序号对应的供应商可访问地址')
        labels, counters, contents = {}, {}, []
        for ordinal, item in enumerate(media):
            kind, role = item['mediaType'], item['mediaRole']
            if item['ordinal'] != ordinal or role not in MEDIA_ROLES.get(kind, set()):
                raise ValueError('引用顺序或媒体角色不受当前适配器支持')
            url = urls[ordinal].get_secret_value()
            # 官方素材引用只用于图片输入，不能放宽生成结果下载地址的 HTTPS 校验。
            if not (kind == 'image' and re.fullmatch(r'asset://asset-[A-Za-z0-9_-]{1,128}', url)):
                validate_output_source(url)
            counters[kind] = counters.get(kind, 0) + 1
            labels[ordinal] = f'{MEDIA_LABELS[kind]} {counters[kind]}'
            field = f'{kind}_url'
            contents.append({'type': field, field: {'url': url}, 'role': 'reference_image' if role == 'reference_person' else role})
        paragraphs = []
        for paragraph in compiled['promptParagraphs']:
            segments = []
            for node in paragraph:
                if node['type'] == 'text':
                    segments.append(node['text'])
                elif node['type'] == 'reference':
                    segments.append('、'.join(labels[ordinal] for ordinal in node['ordinals']))
                else:
                    raise ValueError('不支持的提示词节点')
            paragraphs.append(''.join(segments))
        prompt = '\n'.join(paragraphs)
        if gateway_alias == 'mm-h3' and not prompt.strip():
            raise ValueError('H3 必须填写提示词')
        content = [{'type': 'text', 'text': prompt}, *contents] if contents else prompt
        return {'model': gateway_alias, 'messages': [{'role': 'user', 'content': content}], **parameters}

"""已核实图片端点的单张测试探针，不推断余额或独立鉴权接口。"""
import io
from dataclasses import dataclass
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.entity.vo.credential_test_result_vo import CredentialTestResult
from module_higgsfield.service.image_request_service import ImageRequestService
from module_higgsfield.service.image_response_service import ImageResponseService


class UnsupportedCredentialProbe(ValueError):
    """当前已核实探针无法满足该模型输入要求。"""


@dataclass(repr=False)
class CredentialImageProbeResult:
    diagnostic: CredentialTestResult
    image_fact: object | None = None


class CredentialTestImageProbeService:
    @staticmethod
    def compile(binding):
        if (binding.model_kind != 'image' or binding.model_version is None
                or binding.config.adapter_version != 'videoplus-v1'):
            raise UnsupportedCredentialProbe('尚无该类型的已核实测试探针')
        try:
            capabilities = ModelCapabilities.model_validate(binding.model_version.capabilities)
            supplied = {'n': 1} if 'n' in capabilities.parameters_schema.properties else {}
            payload = ImageRequestService.compile(binding.model_version.gateway_alias, capabilities,
                {'parameters': supplied, 'compiled': {'compilerVersion': 1, 'media': [],
                 'promptParagraphs': [[{'type': 'text', 'text': 'Generate a plain blue circle on a white background.'}]]}})
            if payload.get('n', 1) != 1:
                raise ValueError('测试仅允许生成一张图片')
            return payload
        except (ValueError, ServiceWarning):
            raise UnsupportedCredentialProbe('模型能力配置不满足单张无参考图片测试') from None

    @staticmethod
    def parse(response, *, max_bytes, verify_media):
        """实际媒体验证与正常归档共用，返回用量事实供后续消费登记。"""
        if response.transport != 'response':
            return CredentialImageProbeResult(CredentialTestResult(transport=response.transport,
                authentication='unknown', acceptance='unknown', issue='TRANSPORT_UNKNOWN'))
        status = response.http_status
        if status in {401, 403}:
            return CredentialImageProbeResult(CredentialTestResult(transport='response', httpStatus=status,
                authentication='failed', acceptance='rejected', issue='AUTH_REJECTED'))
        diagnostic = dict(transport='response', httpStatus=status, authentication='unknown',
                          acceptance='unknown', issue='RESPONSE_INVALID')
        fact = None
        try:
            fact = ImageResponseService.parse(status, response.body, max_bytes=max_bytes, expected_count=1)
            invalid = {'OUTPUT_COUNT_MISMATCH', 'DECLARED_FORMAT_INVALID', 'DECLARED_SIZE_INVALID'}
            if len(fact.images) != 1 or fact.rejected_ordinals or invalid.intersection(fact.issues):
                raise ValueError('测试输出数量或内容无效')
            data = fact.images[0].data.get_secret_value()
            if not (data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff'))
                    or (data[:4] == b'RIFF' and data[8:12] == b'WEBP')):
                raise ValueError('测试结果不是支持的图片格式')
            metadata = verify_media(io.BytesIO(data))
            if not metadata['mime_type'].startswith('image/'):
                raise ValueError('测试结果不是图片')
            if fact.declared_format and metadata['mime_type'] != 'image/' + fact.declared_format:
                raise ValueError('测试图片格式与声明不一致')
            if (fact.declared_size and fact.declared_size != 'auto'
                    and fact.declared_size != f'{metadata["width"]}x{metadata["height"]}'):
                raise ValueError('测试图片尺寸与声明不一致')
            diagnostic.update(authentication='passed', acceptance='accepted', issue='NONE',
                              modelVerified=True, outputCount=1)
        except (ValueError, ServiceWarning):
            pass
        return CredentialImageProbeResult(CredentialTestResult(**diagnostic), fact)

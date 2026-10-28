"""按留存 VideoPlus 契约解析响应；不发送请求、不记录原始正文。"""

import json
import re

from pydantic import TypeAdapter, ValidationError

from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult, SafeIdentifier
from module_higgsfield.entity.vo.video_provider_fact_vo import VideoProviderFact
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService

HTTP_SUCCESS_START, HTTP_SUCCESS_END = 200, 300
MAX_DURATION_SECONDS = 86400
MAX_CONTENT_LENGTH = 1_000_000
MAX_TOKEN_COUNT = 9223372036854775807
IDENTIFIER = TypeAdapter(SafeIdentifier)


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    """拒绝重复JSON键，不能让不同解析器对任务编号得出不同结论。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('供应商JSON字段重复')
        result[key] = value
    return result


class VideoPlusResponseService:
    @staticmethod
    def submission(http_status: int, body: object) -> ProviderSubmissionResult:
        facts = {'acceptance': 'unknown', 'transport': 'response', 'httpStatus': http_status}
        if isinstance(body, dict):
            try:
                facts['responseId'] = IDENTIFIER.validate_python(body.get('id'))
            except ValidationError:
                pass
        if not HTTP_SUCCESS_START <= http_status < HTTP_SUCCESS_END or not isinstance(body, dict):
            return ProviderSubmissionResult(**facts)
        try:
            choices = body['choices']
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError('无法唯一确定受理响应')
            content = choices[0]['message']['content']
            if not isinstance(content, str) or len(content) > MAX_CONTENT_LENGTH:
                raise ValueError('受理正文格式无效')
            inner = json.loads(content, object_pairs_hook=unique_object)
            if not isinstance(inner, dict):
                raise ValueError('受理正文不是对象')
            if 'base_resp' in inner:
                base = inner['base_resp']
                if not isinstance(base, dict) or type(base.get('status_code')) is not int or base['status_code'] != 0:
                    raise ValueError('内层响应未证明受理成功')
            task_id = IDENTIFIER.validate_python(inner.get('id'))
            # status 可缺失；出现错误状态时不能仅凭ID宣称已受理。
            if 'status' in inner and inner['status'] not in {
                'queued',
                'running',
                'in_progress',
                'succeeded',
                'completed',
            }:
                raise ValueError('内层受理状态不明确')
            facts.update(acceptance='accepted', upstreamTaskId=task_id)
        except (KeyError, IndexError, TypeError, ValueError, RecursionError):
            pass
        return ProviderSubmissionResult(**facts)

    @staticmethod
    def polling(http_status: int, body: object, *, expected_task_id: str) -> VideoProviderFact:
        IDENTIFIER.validate_python(expected_task_id)
        if not HTTP_SUCCESS_START <= http_status < HTTP_SUCCESS_END or not isinstance(body, dict):
            return VideoProviderFact(upstreamState='unknown', issues=['QUERY_RESPONSE_INVALID'])
        if body.get('id') != expected_task_id:
            return VideoProviderFact(upstreamState='unknown', issues=['TASK_ID_MISMATCH'])
        states = {
            'queued': 'queued',
            'running': 'running',
            'in_progress': 'running',
            'succeeded': 'succeeded',
            'completed': 'succeeded',
            'failed': 'failed',
            'expired': 'failed',
        }
        status = body.get('status')
        state = states.get(status, 'unknown') if isinstance(status, str) else 'unknown'
        fact = VideoProviderFact(upstreamState=state)
        VideoPlusResponseService._metadata(body, fact)
        if state == 'unknown':
            fact.issues.append('UPSTREAM_STATUS_UNKNOWN')
        if state == 'failed':
            fact.failure_reason = status
        VideoPlusResponseService._usage(body, fact)
        if state == 'succeeded':
            if 'completionTokens' not in fact.usage:
                fact.issues.append('USAGE_MISSING')
            content = body.get('content')
            try:
                url = content.get('video_url') if isinstance(content, dict) else None
                output = DiscoveredOutput(ordinal=0, kind='video', sourceUrl=url)
                if 'duration' in fact.actual_parameters:
                    output.actual_metadata.duration_seconds = str(fact.actual_parameters['duration'])
                fact.outputs.append(output)
            except ValueError:
                fact.issues.append('OUTPUT_URL_MISSING_OR_INVALID')
        return fact

    @staticmethod
    def _metadata(body: dict, fact: VideoProviderFact) -> None:
        for name, pattern in (('resolution', r'[1-9][0-9]{1,4}p'), ('ratio', r'[1-9][0-9]{0,3}:[1-9][0-9]{0,3}')):
            value = body.get(name)
            if isinstance(value, str) and re.fullmatch(pattern, value):
                fact.actual_parameters[name] = value
        if type(body.get('duration')) is int and 0 < body['duration'] <= MAX_DURATION_SECONDS:
            fact.actual_parameters['duration'] = body['duration']
        if type(body.get('generate_audio')) is bool:
            fact.actual_parameters['generate_audio'] = body['generate_audio']

    @staticmethod
    def _usage(body: dict, fact: VideoProviderFact) -> None:
        usage = body.get('usage')
        fact.usage_fact = UsageNormalizationService.video(usage)
        if isinstance(usage, dict):
            for source, target in (('completion_tokens', 'completionTokens'), ('total_tokens', 'totalTokens')):
                value = usage.get(source)
                if type(value) is int and 0 <= value <= MAX_TOKEN_COUNT:
                    fact.usage[target] = str(value)
                elif source in usage:
                    fact.issues.append('USAGE_VALUE_INVALID')

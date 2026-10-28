"""按已核实Token语义归一用量，不估算、不乘图片数量、不把缺失记为零。"""

import hashlib
import json
import math
import re

from module_higgsfield.entity.vo.usage_fact_vo import UsageFact

MAX_TOKEN_COUNT = 9223372036854775807
MAX_RAW_INTEGER = 10**100
NUMERIC_EVIDENCE = re.compile(r'[+-]?[0-9]{1,100}(?:\.[0-9]{1,100})?(?:[eE][+-]?[0-9]{1,6})?')


class UsageNormalizationService:
    @staticmethod
    def _safe_value(value: object) -> object:
        """只保留计数证据；任意字符串、嵌套对象可能含秘密，不进入用量表。"""
        if value is None or type(value) is bool:
            return value
        if type(value) is int and abs(value) < MAX_RAW_INTEGER:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if isinstance(value, str) and NUMERIC_EVIDENCE.fullmatch(value):
            return value
        return {'invalidType': type(value).__name__}

    @classmethod
    def _normalize(cls, raw: object, mapping: dict[str, str], *, path: str, parser: str) -> UsageFact:
        quantities, evidence, issues = {}, {}, []
        values = raw if isinstance(raw, dict) else {}
        if not isinstance(raw, dict):
            issues.append('USAGE_OBJECT_MISSING_OR_INVALID')
        for source, target in mapping.items():
            value = values.get(source)
            if source in values:
                evidence[source] = cls._safe_value(value)
            if type(value) is int and 0 <= value <= MAX_TOKEN_COUNT:
                quantities[target] = value
            elif source in values:
                issues.append(source.upper() + '_INVALID')
        complete = 'available' if len(quantities) == len(mapping) else 'partial' if quantities else 'unknown'
        payload = {
            'source_path': path,
            'parser_version': parser,
            'is_cumulative': 'N',
            'raw_usage': evidence,
            'completeness': complete,
            **quantities,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        ).hexdigest()
        return UsageFact(**payload, payload_hash=digest, issues=issues)

    @classmethod
    def image(cls, inner_usage: object) -> UsageFact:
        return cls._normalize(
            inner_usage,
            {'input_tokens': 'input_tokens', 'output_tokens': 'output_tokens'},
            path='choices[0].message.content.usage',
            parser='videoplus-image-usage-v1',
        )

    @classmethod
    def video(cls, task_usage: object) -> UsageFact:
        # completion_tokens代表视频生成Token；total_tokens不重复映射到输入或输出。
        return cls._normalize(
            task_usage,
            {'completion_tokens': 'video_tokens'},
            path='usage',
            parser='videoplus-video-usage-v1',
        )

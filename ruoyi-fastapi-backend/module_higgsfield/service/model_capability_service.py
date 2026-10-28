"""模型配置与请求使用相同规则，未声明能力不默许。"""

from collections import Counter
from module_higgsfield.entity.vo.model_capability_vo import scalar_equal
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ModelCapabilityService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    def parameters(cls, capabilities, supplied, require_complete=True):
        schema = capabilities.parameters_schema
        values = {**capabilities.default_parameters, **supplied}
        for key, value in values.items():
            if key not in schema.properties:
                cls.fail('MODEL_PARAMETER_UNKNOWN', f'模型未开放参数：{key}')
            if not schema.properties[key].accepts(value):
                cls.fail('MODEL_PARAMETER_INVALID', f'参数不符合类型、枚举或范围：{key}')
        required, forbidden = set(schema.required), set()
        for condition in schema.conditions:
            if all(key in values and scalar_equal(values[key], expected) for key, expected in condition.when.items()):
                required.update(condition.require)
                forbidden.update(condition.forbid)
                for key, allowed in condition.allowed.items():
                    if key in values and not any(scalar_equal(values[key], value) for value in allowed):
                        cls.fail('MODEL_PARAMETER_COMBINATION_INVALID', f'当前组合不允许参数值：{key}')
        if forbidden.intersection(values):
            cls.fail('MODEL_PARAMETER_COMBINATION_INVALID', '当前组合包含禁止的参数')
        if require_complete and required.difference(values):
            cls.fail('MODEL_PARAMETER_REQUIRED', '缺少必填参数：' + '、'.join(sorted(required.difference(values))))
        return values

    @classmethod
    def validate_configuration(cls, capabilities):
        # 默认值允许不填必填项，但不能包含未知字段或互相冲突的值。
        cls.parameters(capabilities, {}, require_complete=False)

    @classmethod
    def references(cls, capabilities, compiled, require_complete=True):
        rules = capabilities.reference_rules
        media = compiled['media']
        if len(media) > rules.max_total:
            cls.fail('MODEL_REFERENCE_LIMIT', '引用媒体总数超过模型上限')
        counts = Counter()
        for item in media:
            role = item['mediaRole']
            rule = rules.roles.get(role)
            if rule is None or item['mediaType'] not in rule.media_types:
                cls.fail('REFERENCE_ROLE_UNSUPPORTED', '模型未开放该媒体角色或类型')
            counts[role] += 1
        for role, rule in rules.roles.items():
            if counts[role] > rule.max_count or (require_complete and counts[role] < rule.min_count):
                cls.fail('MODEL_REFERENCE_LIMIT', f'媒体角色数量不符合模型要求：{role}')

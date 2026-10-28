"""版本化模型能力白名单，不支持表达式、远程引用或可执行脚本。"""

from typing import Literal
from math import isfinite
from pydantic import Field, StrictBool, StrictInt, StrictStr, StrictFloat, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput
from module_higgsfield.entity.vo.generation_estimate_vo import GenerationEstimatePolicy

Scalar = StrictStr | StrictBool | StrictInt | StrictFloat


def scalar_equal(left, right):
    # JSON 的布尔值不等于数字，整数和浮点数属于同一数值域。
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


class ParameterRule(WorkspaceInput):
    type: Literal['string', 'boolean', 'integer', 'number']
    title: str = Field(default='', max_length=100)
    description: str = Field(default='', max_length=1000)
    enum: list[Scalar] | None = Field(default=None, min_length=1, max_length=100)
    minimum: StrictInt | StrictFloat | None = None
    maximum: StrictInt | StrictFloat | None = None
    min_length: StrictInt | None = Field(default=None, ge=0, le=50000)
    max_length: StrictInt | None = Field(default=None, ge=0, le=50000)

    def accepts(self, value):
        valid = {
            'string': isinstance(value, str),
            'boolean': isinstance(value, bool),
            'integer': isinstance(value, int) and not isinstance(value, bool),
            'number': isinstance(value, (int, float)) and not isinstance(value, bool),
        }[self.type]
        if not valid:
            return False
        if self.type in ('integer', 'number'):
            if isinstance(value, float) and not isfinite(value):
                return False
            if self.minimum is not None and value < self.minimum:
                return False
            if self.maximum is not None and value > self.maximum:
                return False
        if self.type == 'string':
            if self.min_length is not None and len(value) < self.min_length:
                return False
            if self.max_length is not None and len(value) > self.max_length:
                return False
        return self.enum is None or any(scalar_equal(value, item) for item in self.enum)

    @model_validator(mode='after')
    def coherent(self):
        if self.type not in ('number', 'integer') and (self.minimum is not None or self.maximum is not None):
            raise ValueError('只有数值参数可配置范围')
        if any(isinstance(value, float) and not isfinite(value) for value in (self.minimum, self.maximum)):
            raise ValueError('数值边界必须有限')
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError('数值下限不能大于上限')
        if self.type != 'string' and (self.min_length is not None or self.max_length is not None):
            raise ValueError('只有字符串参数可配置长度')
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError('字符串长度下限不能大于上限')
        if self.enum is not None:
            for index, value in enumerate(self.enum):
                if not self.accepts(value):
                    raise ValueError('枚举值不符合参数类型或范围')
                if any(scalar_equal(value, earlier) for earlier in self.enum[:index]):
                    raise ValueError('枚举值不能重复')
        return self


class ParameterCondition(WorkspaceInput):
    when: dict[str, Scalar] = Field(min_length=1, max_length=30)
    require: list[str] = Field(default_factory=list, max_length=30)
    forbid: list[str] = Field(default_factory=list, max_length=30)
    allowed: dict[str, list[Scalar]] = Field(default_factory=dict, max_length=30)


class ParametersSchema(WorkspaceInput):
    type: Literal['object'] = 'object'
    additional_properties: Literal[False] = False
    properties: dict[str, ParameterRule] = Field(default_factory=dict, max_length=100)
    required: list[str] = Field(default_factory=list, max_length=100)
    conditions: list[ParameterCondition] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def coherent(self):
        names = set(self.properties)
        if any(not key or len(key) > 100 or not key.isascii() or not key.isidentifier() for key in names):
            raise ValueError('参数键必须是非空ASCII标识符')
        if len(set(self.required)) != len(self.required) or not set(self.required) <= names:
            raise ValueError('必填参数必须存在且不能重复')
        for condition in self.conditions:
            if (
                not (set(condition.when) | set(condition.require) | set(condition.forbid) | set(condition.allowed))
                <= names
            ):
                raise ValueError('组合条件引用了未定义的参数')
            if set(condition.require) & set(condition.forbid):
                raise ValueError('组合条件不能同时要求和禁止同一参数')
            for key, value in condition.when.items():
                if not self.properties[key].accepts(value):
                    raise ValueError('组合条件值不符合字段定义')
            for key, values in condition.allowed.items():
                if not values or any(not self.properties[key].accepts(value) for value in values):
                    raise ValueError('条件允许值不能为空且必须符合字段定义')
        return self


class MediaRoleRule(WorkspaceInput):
    media_types: list[Literal['image', 'video', 'audio']] = Field(min_length=1, max_length=3)
    min_count: StrictInt = Field(default=0, ge=0, le=200)
    max_count: StrictInt = Field(ge=1, le=200)

    @model_validator(mode='after')
    def coherent(self):
        if self.min_count > self.max_count or len(set(self.media_types)) != len(self.media_types):
            raise ValueError('媒体数量或类型定义无效')
        return self


class ReferenceRules(WorkspaceInput):
    roles: dict[str, MediaRoleRule] = Field(default_factory=dict, max_length=20)
    max_total: StrictInt = Field(default=0, ge=0, le=200)

    @model_validator(mode='after')
    def coherent(self):
        if any(not role or len(role) > 32 or not role.isascii() or not role.isidentifier() for role in self.roles):
            raise ValueError('媒体角色必须是32字符内的ASCII标识符')
        if sum(rule.min_count for rule in self.roles.values()) > self.max_total:
            raise ValueError('必需媒体数量超过总上限')
        return self


class ModelPresentation(WorkspaceInput):
    aliases: list[StrictStr] = Field(default_factory=list, max_length=30)
    family: str = Field(default='', max_length=100)
    release_label: str = Field(default='', max_length=100)
    market: Literal['domestic', 'overseas', 'unspecified'] = 'unspecified'
    tier: Literal['standard', 'fast', 'unspecified'] = 'unspecified'


class ModelCapabilities(WorkspaceInput):
    variant_dimensions: dict[str, ParameterRule] = Field(default_factory=dict, max_length=30)
    parameters_schema: ParametersSchema
    reference_rules: ReferenceRules
    default_parameters: dict[str, Scalar] = Field(default_factory=dict, max_length=100)
    presentation: ModelPresentation = Field(default_factory=ModelPresentation)
    estimate_policy: GenerationEstimatePolicy | None = None

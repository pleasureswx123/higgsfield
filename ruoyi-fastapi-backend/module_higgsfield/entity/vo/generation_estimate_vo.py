"""经评审的模型级用量上界，不从请求参数推测未知计费用量。"""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator
from typing_extensions import Self

from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput

Count = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$')]
Seconds = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$')]
MAX_TOKEN_COUNT = 9223372036854775807


class UsageUpperBounds(WorkspaceInput):
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    video_tokens: Count | None = None
    image_count: StrictInt | None = Field(default=None, ge=0, le=2147483647)
    output_seconds: Seconds | None = None
    reference_seconds: Seconds | None = None

    @model_validator(mode='after')
    def present_values(self) -> Self:
        if not self.model_fields_set:
            raise ValueError('必须提供经确认的用量上界')
        for name in self.model_fields_set:
            value = getattr(self, name)
            if value is None:
                raise ValueError('未知用量请省略，不能声明为空上界')
            if name.endswith('_tokens') and int(value) > MAX_TOKEN_COUNT:
                raise ValueError('Token用量上界超出bigint范围')
        return self


class GenerationEstimatePolicy(WorkspaceInput):
    schema_version: Literal[1] = 1
    strategy: Literal['fixed_usage_upper_bound']
    evidence_ref: str = Field(min_length=1, max_length=2000)
    scope_statement: str = Field(min_length=1, max_length=4000)
    upper_bounds: UsageUpperBounds

    @model_validator(mode='after')
    def evidence(self) -> Self:
        if not self.evidence_ref.strip() or not self.scope_statement.strip():
            raise ValueError('必须说明来源及覆盖当前能力全部合法请求的范围')
        return self

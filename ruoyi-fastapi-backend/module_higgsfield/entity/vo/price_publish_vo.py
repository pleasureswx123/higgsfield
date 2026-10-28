"""发布时间为明确时区的毫秒值，替换区间须同时提交其版本。"""

from datetime import timezone
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class PriceScheduleInput(WorkspaceInput):
    revision: BigId
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError('操作原因不能为空')
        return value.strip()

    @field_validator('effective_from', 'effective_until', check_fields=False)
    @classmethod
    def utc_milliseconds(cls, value):
        if value is not None:
            value = value.astimezone(timezone.utc)
            if value.microsecond % 1000:
                raise ValueError('生效时间最多支持毫秒精度')
        return value


class PricePublish(PriceScheduleInput):
    effective_from: AwareDatetime
    effective_until: AwareDatetime | None = None
    replace_activation_id: BigId | None = None
    expected_activation_revision: BigId | None = None

    @model_validator(mode='after')
    def valid_range(self):
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError('结束时间必须晚于开始时间')
        if (self.replace_activation_id is None) != (self.expected_activation_revision is None):
            raise ValueError('替换区间与预期版本必须同时指定')
        return self


class PriceActivationEnd(PriceScheduleInput):
    effective_until: AwareDatetime


class PriceHistoryQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

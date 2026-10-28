"""周期起止与金额输入，保留显式时区及十进制精度。"""

from datetime import timezone
from typing import Annotated
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId

BudgetAmount = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,13})(\.[0-9]{1,10})?$')]


class BudgetReason(WorkspaceInput):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def reason_required(cls, value):
        if not value.strip():
            raise ValueError('额度调整原因不能为空')
        return value.strip()


class BudgetPeriodCreate(BudgetReason):
    period_start: AwareDatetime
    period_end: AwareDatetime | None = None
    limit_amount: BudgetAmount

    @field_validator('period_start', 'period_end')
    @classmethod
    def utc_time(cls, value):
        if value is not None:
            value = value.astimezone(timezone.utc)
            if value.microsecond % 1000:
                raise ValueError('周期起止最多支持毫秒精度')
        return value

    @model_validator(mode='after')
    def valid_range(self):
        if self.period_end is not None and self.period_end <= self.period_start:
            raise ValueError('周期终点必须晚于起点')
        return self


class BudgetLimitUpdate(BudgetReason):
    revision: BigId
    new_limit: BudgetAmount


class BudgetPeriodQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

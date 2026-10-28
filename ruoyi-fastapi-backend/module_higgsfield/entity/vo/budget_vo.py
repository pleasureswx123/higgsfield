"""预算定义必须显式指定主体、币种和业务时区。"""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, StrictBool, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class BudgetSubject(WorkspaceInput):
    project_id: BigId | None = None
    user_id: BigId | None = None

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.project_id is None) == (self.user_id is None):
            raise ValueError('预算必须且只能指定一个用户或项目')
        return self


class BudgetCreate(WorkspaceInput):
    subject: BudgetSubject
    purpose: Literal['platform', 'procurement']
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    cycle_kind: Literal['monthly', 'total']
    business_timezone: str = Field(min_length=1, max_length=100)

    @field_validator('business_timezone')
    @classmethod
    def real_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('业务时区必须为有效的 IANA 时区') from None
        return value


class BudgetUpdate(WorkspaceInput):
    revision: BigId
    active: StrictBool


class BudgetQuery(WorkspaceInput):
    subject_type: Literal['project', 'user'] | None = None
    subject_id: BigId | None = None
    purpose: Literal['platform', 'procurement'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode='after')
    def subject_filter(self):
        if self.subject_id and not self.subject_type:
            raise ValueError('按主体编号查询时须明确主体类型')
        return self

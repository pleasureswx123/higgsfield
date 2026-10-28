"""调用记录查询不接受供应商原始载荷或秘密筛选条件。"""
from datetime import UTC
from typing import Literal
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class ProviderCallQuery(WorkspaceInput):
    job_id: BigId | None = None
    account_id: BigId | None = None
    state: Literal['planned', 'sending', 'completed', 'unknown'] | None = None
    from_time: AwareDatetime | None = Field(default=None, alias='from')
    to_time: AwareDatetime | None = Field(default=None, alias='to')
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator('from_time', 'to_time')
    @classmethod
    def utc_boundary(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode='after')
    def valid_window(self):
        if self.from_time is not None and self.to_time is not None and self.from_time >= self.to_time:
            raise ValueError('调用查询结束时间必须晚于开始时间')
        return self

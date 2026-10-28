"""账单受理明确账号、文件和半开账期，时间规范化至 UTC。"""
from datetime import timezone
from typing import Literal
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class ReconciliationCreate(WorkspaceInput):
    account_id: BigId
    upload_id: BigId
    period_start: AwareDatetime
    period_end: AwareDatetime

    @field_validator('period_start', 'period_end')
    @classmethod
    def utc_time(cls, value):
        if value.microsecond % 1000:
            raise ValueError('账期时间最多支持毫秒精度')
        return value.astimezone(timezone.utc)

    @model_validator(mode='after')
    def period(self):
        if self.period_end <= self.period_start:
            raise ValueError('账期终点必须晚于起点')
        return self


class ReconciliationQuery(WorkspaceInput):
    account_id: BigId | None = None
    status: Literal['imported', 'matching', 'confirmed', 'disputed'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


class ReconciliationLineQuery(WorkspaceInput):
    status: Literal['unmatched', 'matched', 'confirmed', 'disputed'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


class ReconciliationConfirm(WorkspaceInput):
    revision: BigId
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('必须填写操作依据')
        return value.strip()


class ReconciliationMatch(ReconciliationConfirm):
    subject_id: BigId


class ReconciliationResolve(ReconciliationMatch):
    observation_id: BigId

"""只开放已实现的恢复动作，管理原因不可为空。"""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class IncidentAction(WorkspaceInput):
    revision: BigId
    action: Literal['retry_archive', 'requery', 'close_tracking', 'confirm_not_accepted']
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ref: str | None = Field(default=None, min_length=1, max_length=255, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')

    @model_validator(mode='after')
    def required_evidence(self):
        if self.action in {'close_tracking', 'confirm_not_accepted'} and not self.evidence_ref:
            raise ValueError('此治理操作必须填写证据引用')
        return self

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('治理原因不能为空')
        return value.strip()

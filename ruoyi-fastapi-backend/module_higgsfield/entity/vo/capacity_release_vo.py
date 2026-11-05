"""名额释放必须有人工核查依据，不能由客户端重试隐式触发。"""
from typing import Literal
from pydantic import Field, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class CapacityRelease(WorkspaceInput):
    reason: str = Field(min_length=1, max_length=4000)
    evidence_ref: str = Field(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')
    acknowledge_supplier_stopped: Literal[True]

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('请填写核查原因')
        return value.strip()

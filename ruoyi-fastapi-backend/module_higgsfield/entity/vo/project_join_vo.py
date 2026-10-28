"""加入申请输入，不允许客户端指定申请人或审批结果字段。"""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class JoinCreate(WorkspaceInput):
    reason: str | None = Field(default=None, max_length=5000)

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value):
        if value is not None:
            if '\x00' in value:
                raise ValueError('说明不能包含空字符')
            return value.strip() or None
        return value


class JoinReview(JoinCreate):
    revision: BigId
    decision: Literal['approved', 'rejected']
    role_id: BigId | None = None

    @model_validator(mode='after')
    def role_matches_decision(self):
        if (self.decision == 'approved') != (self.role_id is not None):
            raise ValueError('批准必须指定角色，拒绝不能分配角色')
        return self


class JoinQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Literal['pending', 'approved', 'rejected', 'cancelled'] | None = None


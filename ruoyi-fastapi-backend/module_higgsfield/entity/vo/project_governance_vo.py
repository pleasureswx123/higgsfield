"""项目治理操作必须携带明确原因及项目修订号。"""
from typing import Literal
from pydantic import Field, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class ProjectGovernanceQuery(WorkspaceInput):
    q: str = Field(default='', max_length=200)
    status: Literal['active', 'paused', 'archived', 'pending_delete'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


class ProjectGovernanceAction(WorkspaceInput):
    revision: BigId
    action: Literal['pause', 'resume', 'archive', 'restore']
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('治理原因不能为空')
        return value.strip()

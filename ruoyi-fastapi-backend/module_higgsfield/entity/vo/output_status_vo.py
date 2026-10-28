"""作品协作标签不承载技术状态变更。"""
from typing import Literal
from pydantic import Field
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class OutputStatusUpdate(WorkspaceInput):
    revision: BigId
    work_status: Literal['none', 'working', 'review', 'approved', 'rejected']
    reason: str = Field(default='', max_length=4000)

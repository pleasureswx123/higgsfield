"""制作与审核动作使用对象修订和固定内容版本双重校验。"""
from typing import Literal
from pydantic import Field
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class ProductionAction(WorkspaceInput):
    revision: BigId
    version_id: BigId
    action: Literal['start', 'submit', 'withdraw', 'request_changes', 'approve', 'reopen']
    reason: str = Field(default='', max_length=2000)


class ProductionAssignment(WorkspaceInput):
    revision: BigId
    performer_id: BigId | None

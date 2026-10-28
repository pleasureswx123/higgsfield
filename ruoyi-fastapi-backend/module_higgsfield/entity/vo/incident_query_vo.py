"""异常队列按可核实的状态类别筛选。"""
from typing import Literal
from pydantic import Field
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class IncidentQuery(WorkspaceInput):
    project_id: BigId | None = None
    state: Literal['submission_unknown', 'blocked', 'upstream_unknown', 'upstream_failed',
                   'archive_failed', 'source_expired', 'billing_disputed'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

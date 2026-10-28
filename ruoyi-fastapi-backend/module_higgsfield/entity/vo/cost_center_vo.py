"""成本中心查询只允许分页，不接收归属修改。"""
from pydantic import Field
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class CostCenterQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

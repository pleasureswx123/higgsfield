"""任务列表筛选，时间范围采用包含起点、不包含终点。"""

from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class GenerationQuery(WorkspaceInput):
    project_id: BigId | None = None
    scope: Literal['project', 'mine'] = 'project'
    kind: Literal['image', 'video', 'chat'] | None = None
    state: (
        Literal['accepted', 'preparing', 'submitting', 'submission_unknown', 'running', 'finished', 'blocked'] | None
    ) = None
    from_time: AwareDatetime | None = Field(default=None, alias='from')
    to_time: AwareDatetime | None = Field(default=None, alias='to')
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode='after')
    def valid_scope(self):
        if self.scope == 'project' and self.project_id is None:
            raise ValueError('项目范围必须提供项目编号')
        if self.from_time and self.to_time and self.from_time >= self.to_time:
            raise ValueError('结束时间必须晚于开始时间')
        return self

"""费用列表按明确用途筛选，不合并平台和采购金额。"""

from typing import Literal
from datetime import timedelta, UTC
from pydantic import Field, AwareDatetime, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class BillingQuery(WorkspaceInput):
    purpose: Literal['platform', 'procurement'] = 'platform'
    scope: Literal['project', 'cost_center'] = 'project'
    cost_center_id: BigId | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    project_id: BigId | None = None
    job_id: BigId | None = None
    user_id: BigId | None = None
    from_time: AwareDatetime | None = Field(default=None, alias='from')
    to_time: AwareDatetime | None = Field(default=None, alias='to')
    state: Literal['pending', 'calculated', 'confirmed', 'disputed'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator('from_time', 'to_time')
    @classmethod
    def utc_boundary(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode='after')
    def valid_window(self):
        if self.scope == 'cost_center' and any((self.project_id, self.job_id, self.user_id)):
            raise ValueError('成本中心费用不能同时按项目、任务或项目执行用户筛选')
        if self.scope == 'project' and self.cost_center_id is not None:
            raise ValueError('成本中心ID仅用于成本中心费用查询')
        if self.from_time is not None and self.to_time is not None:
            if not timedelta(0) < self.to_time - self.from_time <= timedelta(days=366):
                raise ValueError('费用查询区间必须递增且不超过366天')
        return self

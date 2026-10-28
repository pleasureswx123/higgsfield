"""用量汇总显式时间、用途、维度及业务时区。"""

from datetime import UTC, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class UsageQuery(WorkspaceInput):
    from_time: AwareDatetime = Field(alias='from')
    to_time: AwareDatetime = Field(alias='to')
    time_basis: Literal['createTime'] = 'createTime'
    group_by: Literal['project', 'user', 'department', 'model', 'day', 'cost_center']
    scope: Literal['project', 'cost_center'] = 'project'
    cost_center_id: BigId | None = None
    purpose: Literal['platform', 'procurement']
    project_id: BigId | None = None
    user_id: BigId | None = None
    department_id: BigId | None = None
    model_id: BigId | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    business_timezone: str = 'Asia/Shanghai'

    @field_validator('business_timezone')
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError('业务时区无效') from error
        return value

    @model_validator(mode='after')
    def valid_window(self):
        if self.scope == 'cost_center':
            if self.group_by not in {'cost_center', 'day'} or any(
                value is not None for value in (self.project_id, self.user_id, self.department_id, self.model_id)
            ):
                raise ValueError('成本中心汇总仅支持成本中心或日期维度，不能混用项目筛选')
        elif self.cost_center_id is not None or self.group_by == 'cost_center':
            raise ValueError('项目汇总不能使用成本中心筛选或维度')
        self.from_time, self.to_time = self.from_time.astimezone(UTC), self.to_time.astimezone(UTC)
        if not timedelta(0) < self.to_time - self.from_time <= timedelta(days=366):
            raise ValueError('汇总区间必须递增且不超过366天')
        return self


class StudioUsageQuery(UsageQuery):
    purpose: Literal['platform'] = 'platform'
    scope: Literal['project'] = 'project'

    @model_validator(mode='before')
    @classmethod
    def no_actor_override(cls, values):
        if isinstance(values, dict) and any(key in values for key in ('userId', 'user_id')):
            if values.get('userId', values.get('user_id')) is not None:
                raise ValueError('制作端不能指定其他用户筛选')
        return values

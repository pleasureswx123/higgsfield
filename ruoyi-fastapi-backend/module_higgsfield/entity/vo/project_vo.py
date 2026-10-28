from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from common.types import ApiUtcDateTime
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class ProjectRestore(WorkspaceInput):
    revision: BigId
    reason: str = Field(default='', max_length=4000)

    @field_validator('reason')
    @classmethod
    def trim_reason(cls, value):
        return value.strip()


class ProjectArchive(ProjectRestore):
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def require_reason(cls, value):
        if not value:
            raise ValueError('归档原因不能为空')
        return value


class ProjectPause(ProjectRestore):
    """暂停必须记录原因，恢复运行沿用可选原因输入。"""
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def require_reason(cls, value):
        if not value:
            raise ValueError('暂停原因不能为空')
        return value


class ProjectCreate(BaseModel):
    """创建项目输入，仅接受项目名称。"""

    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name', mode='before')
    @classmethod
    def normalize_name(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if any(ord(char) < 32 for char in value):
                raise ValueError('项目名称不能包含控制字符')
        return value


class ProjectUpdate(ProjectCreate):
    """项目基本信息更新必须明确名称及当前修订号。"""
    revision: BigId


class ProjectQuery(BaseModel):
    """项目分页、筛选与稳定排序。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    q: str = Field(default='', max_length=200)
    status: Literal['active', 'paused', 'archived', 'pending_delete'] | None = None
    sort: Literal['created_desc', 'created_asc', 'name_asc'] = 'created_desc'
    hidden: bool = False
    pinned: bool | None = None
    collection_id: BigId | None = None


class ProjectPreferenceModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    project_id: str
    is_pinned: bool = False
    is_hidden: bool = False
    collection_id: str | None = None
    order_num: int = 0
    revision: str = '0'


class ProjectModel(BaseModel):
    """项目输出，大整数标识及版本均传输为字符串。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    id: str
    name: str
    status: str
    revision: str
    create_time: ApiUtcDateTime
    update_time: ApiUtcDateTime
    current_user_role: str
    archived_at: ApiUtcDateTime | None = None
    space_id: str | None = None
    member_count: int | None = None
    preference: ProjectPreferenceModel | None = None

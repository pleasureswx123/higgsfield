"""元素编辑边界：固定版本、显式别名和多图主图约束。"""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput

Category = Literal['character', 'scene', 'prop', 'other']
WorkStatus = Literal['none', 'working', 'review', 'approved', 'rejected']


def meaningful(value):
    value = value.strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError('名称和别名不能为空或包含控制字符')
    return value


class PropertyValue(WorkspaceInput):
    definition_id: BigId
    definition_version: Annotated[StrictInt, Field(ge=1)]
    value: StrictStr | list[StrictStr] | None

    @field_validator('value')
    @classmethod
    def distinct_values(cls, value):
        if isinstance(value, list) and len(set(value)) != len(value):
            raise ValueError('多选属性不能包含重复选项')
        return value


class ElementMedia(WorkspaceInput):
    asset_version_id: BigId
    ordinal: Annotated[StrictInt, Field(ge=0)]
    is_primary: StrictBool


class RevisionContent(WorkspaceInput):
    description: str = ''
    property_values: list[PropertyValue] = Field(default_factory=list)
    media: list[ElementMedia] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_content(self):
        if self.media and sum(item.is_primary for item in self.media) != 1:
            raise ValueError('有图元素必须恰好选择一张主图')
        if len({item.asset_version_id for item in self.media}) != len(self.media):
            raise ValueError('元素不能重复关联同一素材版本')
        if len({item.ordinal for item in self.media}) != len(self.media):
            raise ValueError('媒体顺序不能重复')
        if len({item.definition_id for item in self.property_values}) != len(self.property_values):
            raise ValueError('不能重复填写同一属性定义')
        return self


class ElementFields(RevisionContent):
    name: str = Field(min_length=1, max_length=200)
    alias: str = Field(min_length=1, max_length=100)
    category: Category
    label: str = Field(default='', max_length=100)
    performer_id: BigId | None = None
    work_status: WorkStatus = 'none'

    _name = field_validator('name', 'alias')(meaningful)


class ElementCreate(ElementFields):
    project_id: BigId
    folder_id: BigId | None = None


class ElementSave(ElementFields):
    revision: BigId


class ElementRevisionCreate(RevisionContent):
    revision: BigId


class ElementPatch(WorkspaceInput):
    revision: BigId
    name: str | None = Field(default=None, min_length=1, max_length=200)
    alias: str | None = Field(default=None, min_length=1, max_length=100)
    category: Category | None = None

    @model_validator(mode='after')
    def explicit_fields(self):
        changed = self.model_fields_set - {'revision'}
        if not changed or any(getattr(self, name) is None for name in changed):
            raise ValueError('至少提供一个非空的身份字段')
        for name in changed & {'name', 'alias'}:
            setattr(self, name, meaningful(getattr(self, name)))
        return self


class ElementMove(WorkspaceInput):
    revision: BigId
    folder_id: BigId | None


class ElementRevisionAction(WorkspaceInput):
    revision: BigId


class ElementCopy(WorkspaceInput):
    target_project_id: BigId
    source_revision_id: BigId
    name: str | None = Field(default=None, min_length=1, max_length=200)
    alias: str = Field(min_length=1, max_length=100)

    _alias = field_validator('alias')(meaningful)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        return meaningful(value) if value is not None else value


class ElementLabel(WorkspaceInput):
    revision: BigId
    label: str = Field(max_length=100)


class ElementQuery(WorkspaceInput):
    project_id: BigId | None = None
    scope: Literal['project', 'mine'] = 'project'
    mine_filter: Literal['all', 'created', 'favorites'] = 'all'
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
    q: str = Field(default='', max_length=200)
    category: Category | None = None
    work_status: WorkStatus | None = None
    folder_id: BigId | None = None
    status_group: Literal['active', 'drafts'] | None = None

    @model_validator(mode='after')
    def project_required(self):
        if self.scope == 'project' and not self.project_id:
            raise ValueError('项目元素列表必须指定项目')
        if self.scope != 'mine' and self.mine_filter != 'all':
            raise ValueError('创建或收藏筛选仅适用于我的元素')
        return self


class PropertyDefinitionFields(WorkspaceInput):
    name: str = Field(min_length=1, max_length=200)
    value_type: Literal['text', 'multi_select']
    options: list[StrictStr] = Field(default_factory=list)

    _name = field_validator('name')(meaningful)

    @model_validator(mode='after')
    def option_shape(self):
        if self.value_type == 'text' and self.options:
            raise ValueError('文本属性不能配置选项')
        if self.value_type == 'multi_select' and not self.options:
            raise ValueError('多选属性至少配置一个选项')
        if any(not option.strip() or option != option.strip() for option in self.options):
            raise ValueError('选项不能为空或带有首尾空白')
        if len(set(self.options)) != len(self.options):
            raise ValueError('选项不能重复')
        return self


class PropertyDefinitionCreate(PropertyDefinitionFields):
    property_key: str = Field(min_length=1, max_length=100, pattern=r'^[a-z][a-z0-9_]*$')

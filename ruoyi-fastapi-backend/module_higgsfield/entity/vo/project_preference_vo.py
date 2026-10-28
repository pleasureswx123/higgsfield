"""个人集合与偏好输入；省略字段与显式清空分别处理。"""
from typing import Annotated

from pydantic import AfterValidator, Field, StrictBool, field_validator, model_validator

from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput, valid_bigint


InitialRevision = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$'), AfterValidator(valid_bigint)]
OrderNumber = Annotated[int, Field(strict=True, ge=-2147483648, le=2147483647)]


class CollectionCreate(WorkspaceInput):
    name: str = Field(min_length=1, max_length=200)
    order_num: OrderNumber = 0

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value or '\x00' in value:
            raise ValueError('集合名称不能为空或包含空字符')
        return value


class CollectionQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CollectionUpdate(WorkspaceInput):
    revision: BigId
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-f]{6}$')
    order_num: OrderNumber | None = None

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        return CollectionCreate.clean_name(value) if value is not None else value

    @field_validator('description')
    @classmethod
    def clean_description(cls, value):
        if value is not None and '\x00' in value:
            raise ValueError('集合说明不能包含空字符')
        return value

    @model_validator(mode='after')
    def require_change(self):
        if not self.model_fields_set - {'revision'}:
            raise ValueError('至少修改一个集合字段')
        for field in ('name', 'order_num'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError('名称和排序不能清空')
        return self


class PreferenceUpdate(WorkspaceInput):
    revision: InitialRevision
    is_pinned: StrictBool | None = None
    is_hidden: StrictBool | None = None
    collection_id: BigId | None = None
    order_num: OrderNumber | None = None

    @model_validator(mode='after')
    def require_change(self):
        if not self.model_fields_set - {'revision'}:
            raise ValueError('至少修改一个个人偏好字段')
        for field in ('is_pinned', 'is_hidden', 'order_num'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError('置顶、隐藏和排序不能清空')
        return self

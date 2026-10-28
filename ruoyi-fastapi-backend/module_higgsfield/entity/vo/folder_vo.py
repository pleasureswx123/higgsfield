import unicodedata
from typing import Literal

from pydantic import Field, field_validator

from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput

Color = Literal['lime', 'cyan', 'slate', 'violet', 'purple', 'pink', 'yellow']


def normalized_name(value: str) -> str:
    return unicodedata.normalize('NFKC', value.strip()).casefold()


class FolderCreate(WorkspaceInput):
    parent_id: BigId | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str = ''
    color: Color = 'lime'
    folder_kind: Literal['media', 'element'] = 'media'

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if (
            not value
            or len(value) > 200
            or len(normalized_name(value)) > 200
            or any(unicodedata.category(c) == 'Cc' for c in value)
        ):
            raise ValueError('目录名称不能为空、包含控制字符或超过200字符')
        return value


class FolderPatch(WorkspaceInput):
    revision: BigId
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    color: Color | None = None
    order_num: int | None = Field(default=None, ge=-2147483648, le=2147483647)

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        return FolderCreate.valid_name(value) if value is not None else value


class FolderMove(WorkspaceInput):
    revision: BigId
    parent_id: BigId | None


class FolderCopy(WorkspaceInput):
    revision: BigId
    target_parent_id: BigId | None
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        return FolderCreate.valid_name(value) if value is not None else value


class FolderRestore(WorkspaceInput):
    revision: BigId
    target_parent_id: BigId | None = None


class FolderQuery(WorkspaceInput):
    parent_id: BigId | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
    q: str = Field(default='', max_length=200)
    folder_kind: Literal['media', 'element'] = 'media'
    sort: Literal['createdAsc', 'createdDesc', 'updatedDesc', 'nameAsc', 'nameDesc'] = 'nameAsc'

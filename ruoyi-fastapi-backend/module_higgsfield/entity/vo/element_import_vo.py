"""元素导入受理与分页边界，不允许客户端指定解析状态。"""
from typing import Literal
from pydantic import Field, StrictBool, StrictInt
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId
from module_higgsfield.entity.vo.element_vo import PropertyValue


class ElementImportCreate(WorkspaceInput):
    project_id: BigId
    upload_id: BigId
    schema_version: StrictInt = Field(ge=1, le=1)
    include_project_name: StrictBool = True


class ElementImportRowsQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    state: Literal['pending', 'succeeded', 'failed'] | None = None


class ElementImportCandidateInput(WorkspaceInput):
    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    name: str = Field(max_length=20000)
    alias: str = Field(max_length=20000)
    category: str = Field(max_length=20000)
    description: str = Field(default='', max_length=20000)
    property_values: list[PropertyValue] = Field(default_factory=list, max_length=50)


class ElementImportRowEdit(WorkspaceInput):
    revision: BigId
    candidate: ElementImportCandidateInput
    is_selected: StrictBool


class ElementImportConfirm(WorkspaceInput):
    revision: BigId

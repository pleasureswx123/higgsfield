"""测试请求必须明确确认潜在费用，不接受隐式布尔转换。"""
from pydantic import Field, StrictBool, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class CredentialTestCreate(WorkspaceInput):
    model_version_id: BigId | None = None
    cost_center_id: BigId
    acknowledge_potential_charge: StrictBool

    @field_validator('acknowledge_potential_charge')
    @classmethod
    def acknowledged(cls, value):
        if not value:
            raise ValueError('必须确认测试可能产生费用')
        return value


class CredentialTestPage(WorkspaceInput):
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

from typing import Literal
from pydantic import Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities, Scalar


class ModelCreate(WorkspaceInput):
    connection_id: BigId
    code: str = Field(min_length=1, max_length=100, pattern=r'^[a-z][a-z0-9_-]*$')
    display_name: str = Field(min_length=1, max_length=200)
    kind: Literal['image', 'video']

    @field_validator('display_name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError('模型名称不能为空或包含控制字符')
        return value.strip()


class ModelVersionCreate(WorkspaceInput):
    gateway_alias: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]*$')
    underlying_model_id: str | None = Field(default=None, min_length=1, max_length=255)
    region: str = Field(min_length=1, max_length=32, pattern=r'^[a-z][a-z0-9_-]*$')
    capabilities: ModelCapabilities
    schema_version: Literal[1] = 1


class ModelVariantCreate(WorkspaceInput):
    dimensions: dict[str, Scalar] = Field(max_length=30)


class ModelVersionPatch(WorkspaceInput):
    revision: BigId
    gateway_alias: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]*$'
    )
    underlying_model_id: str | None = Field(default=None, min_length=1, max_length=255)
    capabilities: ModelCapabilities | None = None

    @model_validator(mode='after')
    def changes(self):
        fields = self.model_fields_set - {'revision'}
        if not fields or any(getattr(self, key) is None for key in fields - {'underlying_model_id'}):
            raise ValueError('必须提供修改字段，只有底层模型标识允许显式清空')
        return self


class ModelVersionAction(WorkspaceInput):
    revision: BigId
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator('reason')
    @classmethod
    def meaningful(cls, value):
        if not value.strip() or any(ord(char) < 32 and char not in '\n\t' for char in value):
            raise ValueError('操作原因不能为空或包含控制字符')
        return value.strip()


class ModelVersionVerify(ModelVersionAction):
    verification_ref: str = Field(min_length=1, max_length=2000)

    @field_validator('verification_ref')
    @classmethod
    def evidence(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError('联调证据位置不能为空或包含控制字符')
        return value.strip()


class ModelQuery(WorkspaceInput):
    connection_id: BigId | None = None
    kind: Literal['image', 'video'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)

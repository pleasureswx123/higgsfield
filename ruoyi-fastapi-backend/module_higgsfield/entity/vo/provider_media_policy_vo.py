"""已核实模型版本的直传策略；不把供应商MB声明换算成默认字节限制。"""

from typing import Literal

from pydantic import Field, StrictInt, field_validator

from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class DirectUploadPolicy(WorkspaceInput):
    roles: list[Literal['first_frame', 'reference_image', 'reference_video']] = Field(min_length=1)
    mime_limits: dict[str, StrictInt] = Field(min_length=1)
    required_seconds: StrictInt = Field(ge=1, le=604800)
    evidence_ref: str = Field(min_length=1, max_length=1000)

    @field_validator('mime_limits')
    @classmethod
    def valid_limits(cls, values: dict[str, int]) -> dict[str, int]:
        if any(not mime.startswith(('image/', 'video/')) or limit <= 0 for mime, limit in values.items()):
            raise ValueError('只允许显式配置图片和视频的正整数字节上限')
        return values


class ProviderMediaPolicies(WorkspaceInput):
    model_versions: dict[str, DirectUploadPolicy] = Field(default_factory=dict)

    @field_validator('model_versions')
    @classmethod
    def valid_versions(cls, values: dict[str, DirectUploadPolicy]) -> dict[str, DirectUploadPolicy]:
        if any(not value.isascii() or not value.isdecimal() or value.startswith('0') for value in values):
            raise ValueError('媒体策略必须绑定精确模型版本ID')
        return values

"""管理证据上传不接受项目标识或素材用途。"""
from typing import Literal

from pydantic import Field, field_validator
from module_higgsfield.entity.vo.asset_vo import UploadCreate, Sha256
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class DocumentUploadCreate(WorkspaceInput):
    purpose: Literal['price_source', 'reconciliation']
    file_name: str = Field(min_length=1, max_length=255)
    byte_size: BigId
    mime_type: Literal['text/plain', 'text/csv', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'image/png', 'image/jpeg', 'image/webp']
    sha256: Sha256 | None = None

    @field_validator('file_name')
    @classmethod
    def safe_name(cls, value):
        return UploadCreate.safe_name(value)

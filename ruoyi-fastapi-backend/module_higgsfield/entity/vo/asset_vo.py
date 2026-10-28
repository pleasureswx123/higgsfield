from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput

Sha256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]


class UploadCreate(WorkspaceInput):
    project_id: BigId
    file_name: str = Field(min_length=1, max_length=255)
    byte_size: BigId
    mime_type: Literal['image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm',
                       'text/csv', 'text/plain', 'text/markdown', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/pdf',
                       'text/html', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']
    sha256: Sha256 | None = None

    @field_validator('file_name')
    @classmethod
    def safe_name(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError('文件展示名不能为空或包含控制字符')
        return value.strip()


class UploadComplete(WorkspaceInput):
    sha256: Sha256


class AssetCreate(WorkspaceInput):
    project_id: BigId
    upload_id: BigId
    name: str = Field(min_length=1, max_length=200)
    folder_id: BigId | None = None

    @field_validator('name')
    @classmethod
    def safe_name(cls, value):
        return UploadCreate.safe_name(value)


class AssetVersionCreate(WorkspaceInput):
    revision: BigId
    upload_id: BigId


class OutputToAsset(WorkspaceInput):
    project_id: BigId
    folder_id: BigId | None = None
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def safe_name(cls, value):
        return UploadCreate.safe_name(value)


class AssetAction(WorkspaceInput):
    revision: BigId


class AssetPatch(AssetAction):
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def safe_name(cls, value):
        return UploadCreate.safe_name(value)


class LibraryQuery(WorkspaceInput):
    from_time: AwareDatetime | None = Field(default=None, alias='from')
    to_time: AwareDatetime | None = Field(default=None, alias='to')
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)
    folder_id: BigId | None = None
    include_descendants: bool = False
    q: str = Field(default='', max_length=200)
    kind: Literal['asset'] = 'asset'
    file_type: Literal['image', 'video', 'pdf', 'txt', 'md', 'html', 'docx', 'pptx'] | None = None
    activity: Literal['uploaded', 'generated', 'liked', 'downloaded'] | None = None

    @model_validator(mode='after')
    def valid_window(self):
        if self.from_time and self.to_time and self.from_time >= self.to_time:
            raise ValueError('结束时间必须晚于开始时间')
        return self


class LibraryMove(WorkspaceInput):
    entry_id: BigId
    revision: BigId
    folder_id: BigId | None


class AssetStatus(AssetAction):
    work_status: Literal['none', 'working', 'review', 'approved', 'rejected']

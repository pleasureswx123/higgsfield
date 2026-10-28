"""临时供应商媒体地址；秘密URL不可进入普通日志。"""

from typing import Literal

from pydantic import AwareDatetime, Field, SecretStr, StrictInt

from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class ProviderUploadedMedia(WorkspaceInput):
    source_url: SecretStr = Field(repr=False)
    expires_at: AwareDatetime
    file_name: str = Field(min_length=1, max_length=255)
    asset_type: Literal['image', 'video']
    content_type: str
    byte_size: StrictInt = Field(gt=0)
    issues: list[str] = Field(default_factory=list)

"""仅供归档工作进程提交的已验证文件事实，不接受客户端指定文件状态。"""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArchiveFileFacts(BaseModel):
    model_config = ConfigDict(extra='forbid')

    storage_key: str = Field(pattern=r'^media/[a-f0-9]{32}$')
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    byte_size: int = Field(strict=True, gt=0, le=9223372036854775807)
    mime_type: str = Field(pattern=r'^(image/(png|jpeg|webp)|video/(mp4|webm))$')
    width: int = Field(strict=True, gt=0, le=2147483647)
    height: int = Field(strict=True, gt=0, le=2147483647)
    seconds: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)

    @model_validator(mode='after')
    def media_duration(self) -> Self:
        if self.mime_type.startswith('video/') != (self.seconds is not None):
            raise ValueError('视频必须提供实际时长，图片不得提供视频时长')
        return self

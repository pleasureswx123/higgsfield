"""仅供归档工作进程提交的已验证文件事实，不接受客户端指定文件状态。"""

from decimal import Decimal
from typing import Self, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArchiveDownloadProgress(BaseModel):
    """只保留字节、阶段及计时，不接收地址、响应正文或凭据。"""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    stage: Literal['downloading', 'verifying', 'complete', 'failed']
    errorCode: Literal['timeout', 'network', 'invalid_response', 'storage_or_state'] | None = None
    bytes: int = Field(strict=True, ge=0)
    totalBytes: int | None = Field(default=None, strict=True, gt=0)
    elapsedSeconds: float = Field(ge=0)
    dnsSeconds: float | None = Field(default=None, ge=0)
    firstByteSeconds: float | None = Field(default=None, ge=0)
    requests: int = Field(strict=True, ge=0)
    resumeCount: int = Field(strict=True, ge=0)
    receivedBytes: int = Field(strict=True, ge=0)
    connections: int = Field(strict=True, ge=1, le=4)

    @model_validator(mode='after')
    def bounded(self):
        if self.totalBytes is not None and self.bytes > self.totalBytes:
            raise ValueError('已下载字节不能超过总字节')
        return self


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

"""已落盘加密证据的白名单登记字段。"""

from pydantic import BaseModel, ConfigDict, Field


class ResponseFileFacts(BaseModel):
    model_config = ConfigDict(extra='forbid')

    storage_key: str = Field(pattern=r'^provider-evidence/[a-f0-9]{32}$')
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    byte_size: int = Field(strict=True, gt=0, le=268435968)

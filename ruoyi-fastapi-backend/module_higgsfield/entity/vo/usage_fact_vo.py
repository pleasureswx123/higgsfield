"""可登记用量事实；空值表示未知，不等同于零。"""

from typing import Literal
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class UsageFact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    input_tokens: int | None = Field(default=None, strict=True, ge=0, le=9223372036854775807)
    output_tokens: int | None = Field(default=None, strict=True, ge=0, le=9223372036854775807)
    video_tokens: int | None = Field(default=None, strict=True, ge=0, le=9223372036854775807)
    output_seconds: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=6)
    image_count: int | None = Field(default=None, strict=True, ge=0, le=2147483647)
    completeness: Literal['available', 'partial', 'unknown']
    source_path: str
    parser_version: str
    is_cumulative: Literal['Y', 'N'] = 'N'
    raw_usage: dict
    issues: list[str] = Field(default_factory=list)
    payload_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

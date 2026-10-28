"""图片网关参数的契约上限；模型能力版本仍可设置更严格限制。"""

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_EDGE, SIZE_STEP, MAX_RATIO = 3840, 16, 3


class ImageRequestParameters(BaseModel):
    model_config = ConfigDict(extra='forbid')

    n: int = Field(default=1, strict=True, ge=1, le=10)
    size: str = 'auto'
    quality: Literal['low', 'medium', 'high', 'auto'] = 'auto'
    output_format: Literal['png', 'jpeg', 'webp'] = 'png'
    output_compression: int | None = Field(default=None, strict=True, ge=0, le=100)
    moderation: Literal['auto'] = 'auto'

    @model_validator(mode='after')
    def dimensions(self) -> Self:
        if self.size != 'auto':
            if not re.fullmatch(r'[1-9][0-9]{0,3}x[1-9][0-9]{0,3}', self.size):
                raise ValueError('图片尺寸必须为auto或WxH')
            width, height = (int(part) for part in self.size.split('x'))
            if max(width, height) > MAX_EDGE or width % SIZE_STEP or height % SIZE_STEP:
                raise ValueError('图片尺寸超限或不是16的倍数')
            if max(width, height) > MAX_RATIO * min(width, height):
                raise ValueError('图片宽高比不能超过3:1')
        return self

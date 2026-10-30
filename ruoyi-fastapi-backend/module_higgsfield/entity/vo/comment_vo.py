"""评论固定媒体目标、视频时间与归一化标注输入契约。"""
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput

Coordinate = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class PointGeometry(WorkspaceInput):
    x: Coordinate
    y: Coordinate


class RectGeometry(PointGeometry):
    width: Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)]
    height: Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)]

    @model_validator(mode='after')
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError('矩形不能超出图片边界')
        return self


class PathGeometry(WorkspaceInput):
    points: list[PointGeometry] = Field(min_length=2, max_length=256)


class Annotation(WorkspaceInput):
    shape: Literal['point', 'rect', 'path']
    geometry: dict
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    source_width: int = Field(strict=True, gt=0, le=100000)
    source_height: int = Field(strict=True, gt=0, le=100000)

    @model_validator(mode='after')
    def validate_geometry(self):
        model = {'point': PointGeometry, 'rect': RectGeometry, 'path': PathGeometry}[self.shape]
        self.geometry = model.model_validate(self.geometry).model_dump()
        self.color = self.color.lower()
        return self


class ThreadTarget(WorkspaceInput):
    asset_version_id: BigId | None = None
    output_id: BigId | None = None

    @model_validator(mode='after')
    def exactly_one(self):
        if (self.asset_version_id is None) == (self.output_id is None):
            raise ValueError('评论必须且只能绑定一个具体素材版本或作品')
        return self


class ThreadCreate(WorkspaceInput):
    target: ThreadTarget


class CommentPage(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)


class ThreadQuery(ThreadTarget, CommentPage):
    pass


class CommentBody(WorkspaceInput):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator('body')
    @classmethod
    def meaningful_body(cls, value):
        if not value.strip() or '\x00' in value:
            raise ValueError('评论不能为空或包含空字符')
        return value


class CommentCreate(CommentBody):
    parent_id: BigId | None = None
    video_time: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6, allow_inf_nan=False)
    annotations: list[Annotation] = Field(default_factory=list, max_length=100)

    @field_validator('video_time', mode='before')
    @classmethod
    def decimal_string(cls, value):
        if value is not None and not isinstance(value, str):
            raise ValueError('视频时间点必须使用十进制字符串')
        return value


class CommentPatch(CommentBody):
    revision: BigId
    annotations: list[Annotation] = Field(default_factory=list, max_length=100)


class CommentDelete(WorkspaceInput):
    revision: BigId


class ThreadPatch(WorkspaceInput):
    revision: BigId
    action: Literal['resolve', 'reopen', 'delete']

class ReactionPatch(WorkspaceInput):
    emoji: str = Field(min_length=1, max_length=32)
    active: bool

    @field_validator('emoji')
    @classmethod
    def supported_emoji(cls, value):
        if value not in '😀 😃 😄 😁 😆 😅 😂 🤣 😊 🙂 🙃 😉 😍 🥰 😘 😋 😎 🤔 😮 😢 😭 😡 👍 👎 ❤️ 🎉 ✅ 👀 🙏 🔥 💯 🚀'.split():
            raise ValueError('不支持的回应表情')
        return value

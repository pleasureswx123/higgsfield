from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


def valid_bigint(value):
    if int(value) > 9223372036854775807:
        raise ValueError('编号或版本超过 bigint 范围')
    return value


BigId = Annotated[str, Field(pattern=r'^[1-9][0-9]{0,18}$'), AfterValidator(valid_bigint)]


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra='forbid', alias_generator=to_camel, populate_by_name=True)


class TextMark(WorkspaceInput):
    type: Literal['bold', 'italic', 'link']
    href: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def link_shape(self):
        if (self.type == 'link') != bool(self.href):
            raise ValueError('链接标记必须提供地址，其他标记不能提供地址')
        return self

    @field_validator('href')
    @classmethod
    def safe_link(cls, value):
        if value is not None:
            url = urlsplit(value)
            if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
                raise ValueError('链接仅支持不含凭据的 HTTP/HTTPS 地址')
            if any(ord(char) < 33 for char in value):
                raise ValueError('链接包含非法字符')
        return value


class TextNode(WorkspaceInput):
    type: Literal['text'] = 'text'
    text: str = Field(max_length=20000)
    marks: list[TextMark] = Field(default_factory=list, max_length=3)


class Paragraph(WorkspaceInput):
    type: Literal['paragraph'] = 'paragraph'
    content: list[TextNode] = Field(default_factory=list, max_length=100)


class BriefBody(WorkspaceInput):
    schema_version: Literal[1] = 1
    type: Literal['doc'] = 'doc'
    content: list[Paragraph] = Field(default_factory=list, max_length=200)

    @field_validator('content')
    @classmethod
    def bounded_content(cls, value):
        if sum(len(node.text) for paragraph in value for node in paragraph.content) > 50000:
            raise ValueError('简报正文最多 50000 字符')
        return value


class BriefUpdate(WorkspaceInput):
    revision: BigId
    body: BriefBody


class MemberAdd(WorkspaceInput):
    user_id: BigId
    role_id: BigId


class MemberUpdate(WorkspaceInput):
    revision: BigId
    role_id: BigId


class MemberQuery(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Literal['active', 'removed'] = 'active'


class ProjectPermissionUpdate(WorkspaceInput):
    revision: Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$'), AfterValidator(valid_bigint)]
    overrides: dict[str, dict[str, Literal['none', 'own', 'project']]] = Field(max_length=3)

    @field_validator('overrides')
    @classmethod
    def bounded_permissions(cls, value):
        if any(len(permissions) > 40 for permissions in value.values()):
            raise ValueError('权限数量超出限制')
        return value


class OwnershipTransfer(WorkspaceInput):
    user_id: BigId
    revision: BigId
    target_revision: BigId

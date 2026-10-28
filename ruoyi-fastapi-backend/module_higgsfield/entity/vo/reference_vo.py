"""引用候选与固定版本输入，不接受外部媒体地址。"""

from typing import Literal
from pydantic import Field, StrictInt, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import TextNode
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class ReferenceQuery(WorkspaceInput):
    project_id: BigId
    q: str = Field(default='', max_length=200)
    kind: Literal['asset', 'element'] | None = None
    element_id: BigId | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)


    @model_validator(mode='after')
    def element_filter_kind(self):
        if self.element_id is not None and self.kind != 'element':
            raise ValueError('按元素ID定位候选时必须指定元素类型')
        return self


class Reference(WorkspaceInput):
    reference_key: BigId
    asset_version_id: BigId
    element_revision_id: BigId | None = None
    media_role: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_]*$')
    ordinal: StrictInt = Field(ge=0, le=2147483647)


class ReferenceUpdatesQuery(WorkspaceInput):
    project_id: BigId
    element_revision_ids: list[BigId] = Field(max_length=200)


class MentionNode(WorkspaceInput):
    type: Literal['mention']
    reference_key: BigId


class PromptParagraph(WorkspaceInput):
    type: Literal['paragraph'] = 'paragraph'
    content: list[TextNode | MentionNode] = Field(default_factory=list, max_length=100)


class PromptBody(WorkspaceInput):
    schema_version: Literal[1] = 1
    type: Literal['doc'] = 'doc'
    content: list[PromptParagraph] = Field(default_factory=list, max_length=200)

    @field_validator('content')
    @classmethod
    def bounded_text(cls, value):
        if (
            sum(len(node.text) for paragraph in value for node in paragraph.content if isinstance(node, TextNode))
            > 50000
        ):
            raise ValueError('提示词正文最多50000字符')
        return value


class ReferenceInput(WorkspaceInput):
    prompt: PromptBody
    references: list[Reference] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def consistent_keys(self):
        ordinals, sources, media = set(), {}, set()
        for item in self.references:
            if item.ordinal in ordinals:
                raise ValueError('引用顺序不能重复')
            ordinals.add(item.ordinal)
            source = (
                ('element', item.element_revision_id) if item.element_revision_id else ('asset', item.asset_version_id)
            )
            if item.reference_key in sources and sources[item.reference_key] != source:
                raise ValueError('同一引用键必须关联同一元素修订或同一素材版本')
            sources[item.reference_key] = source
            identity = (item.reference_key, item.asset_version_id, item.media_role)
            if identity in media:
                raise ValueError('同一引用键不能重复选择相同媒体和角色')
            media.add(identity)
        for paragraph in self.prompt.content:
            for node in paragraph.content:
                if isinstance(node, MentionNode) and node.reference_key not in sources:
                    raise ValueError('提示词提及必须关联实际引用')
        return self

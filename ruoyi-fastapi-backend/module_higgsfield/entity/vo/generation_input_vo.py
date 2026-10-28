"""正式生成输入不接受客户端指定凭据、计价规格或金额。"""

from typing import Literal, Self

from pydantic import Field, JsonValue, model_serializer, model_validator

from module_higgsfield.entity.vo.project_workspace_vo import BigId
from module_higgsfield.entity.vo.reference_vo import Reference, ReferenceInput


class GenerationInput(ReferenceInput):
    project_id: BigId
    kind: Literal['image', 'video']
    model_version_id: BigId
    parameters: dict[str, JsonValue]
    references: list[Reference] = Field(max_length=200)
    folder_id: BigId | None = None
    draft_id: BigId | None = None
    draft_revision: BigId | None = None
    source_job_id: BigId | None = None
    target_element_id: BigId | None = None
    estimate_token: str | None = Field(default=None, min_length=1, max_length=4096)

    @model_validator(mode='after')
    def paired_draft(self) -> Self:
        if self.target_element_id is not None and self.kind != 'image':
            raise ValueError('目标元素仅支持图片生成')
        if (self.draft_id is None) != (self.draft_revision is None):
            raise ValueError('草稿ID与修订必须同时提供')
        return self

    @model_serializer(mode='wrap')
    def serialize_request(self, handler):
        # 新增可选上下文不能改变未使用此能力的历史幂等/估价签名。
        data = handler(self)
        if self.target_element_id is None:
            data.pop('targetElementId', None)
            data.pop('target_element_id', None)
        return data

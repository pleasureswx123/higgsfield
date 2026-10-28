"""私有草稿输入，提示词及引用沿用同一结构契约。"""

from typing import Literal
from pydantic import Field, JsonValue, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput
from module_higgsfield.entity.vo.reference_vo import PromptBody, Reference, ReferenceInput


class ReturnContext(WorkspaceInput):
    route: Literal['project-elements']
    project_id: BigId
    element_id: BigId


class DraftBody(WorkspaceInput):
    schema_version: Literal[1] = 1
    prompt: PromptBody
    model_version_id: BigId | None = None
    folder_id: BigId | None = None
    source_job_id: BigId | None = None
    target_element_id: BigId | None = None
    return_context: ReturnContext | None = None
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class DraftContent(WorkspaceInput):
    body: DraftBody
    references: list[Reference] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def reference_contract(self):
        ReferenceInput(prompt=self.body.prompt, references=self.references)
        return self


class DraftCreate(DraftContent):
    project_id: BigId
    kind: Literal['image', 'video']


class DraftUpdate(DraftContent):
    revision: BigId


class DraftQuery(WorkspaceInput):
    project_id: BigId
    kind: Literal['image', 'video'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

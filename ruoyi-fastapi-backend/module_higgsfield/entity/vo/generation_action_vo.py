"""任务取消操作的并发版本与说明。"""

from pydantic import Field, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class GenerationRetryArchive(WorkspaceInput):
    revision: BigId
    output_ids: list[BigId] | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator('output_ids')
    @classmethod
    def distinct_outputs(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError('输出编号不能重复')
        return value


class GenerationCancel(WorkspaceInput):
    revision: BigId
    reason: str = Field(default='用户取消尚未提交的任务', min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, value):
        if not value.strip():
            raise ValueError('取消原因不能为空')
        return value.strip()

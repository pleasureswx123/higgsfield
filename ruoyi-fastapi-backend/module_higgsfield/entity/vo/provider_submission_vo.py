"""适配器归一化的异步受理事实，不接收原始响应或自由文本错误。"""

from typing import Annotated, Literal, Self

from pydantic import Field, StrictInt, model_validator

from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput

SafeIdentifier = Annotated[str, Field(min_length=1, max_length=255, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:-]*$')]
HTTP_SUCCESS_START, HTTP_SUCCESS_END = 200, 300


class ProviderSynchronousResult(WorkspaceInput):
    """供应商已直接返回完整结果，不虚构异步任务编号。"""

    http_status: StrictInt = Field(ge=200, le=299)
    response_id: SafeIdentifier | None = None
    outputs: list[DiscoveredOutput] = Field(min_length=1, max_length=1000)


class ProviderSubmissionResult(WorkspaceInput):
    acceptance: Literal['accepted', 'rejected', 'unknown']
    transport: Literal['response', 'timeout', 'network_error']
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    business_code: str | None = Field(default=None, max_length=100, pattern=r'^[A-Za-z0-9_.:-]+$')
    response_id: SafeIdentifier | None = None
    upstream_task_id: SafeIdentifier | None = None

    @model_validator(mode='after')
    def consistent(self) -> Self:
        if self.transport != 'response':
            if self.acceptance != 'unknown' or any(
                value is not None
                for value in (self.http_status, self.business_code, self.response_id, self.upstream_task_id)
            ):
                raise ValueError('未收到响应只能登记提交未知，不能伪造响应事实')
        elif self.http_status is None:
            raise ValueError('响应事实必须包含HTTP状态')
        if self.acceptance == 'accepted' and not self.upstream_task_id:
            raise ValueError('异步受理必须有内层上游任务ID')
        if self.acceptance == 'accepted' and not HTTP_SUCCESS_START <= self.http_status < HTTP_SUCCESS_END:
            raise ValueError('异步受理事实必须来自成功HTTP响应')
        if self.acceptance != 'accepted' and self.upstream_task_id:
            raise ValueError('未确认受理不能绑定任务ID')
        return self

"""视频查询归一化事实；输出、用量与上游状态分别表达。"""

from typing import Literal

from pydantic import Field

from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput
from module_higgsfield.entity.vo.usage_fact_vo import UsageFact


class VideoProviderFact(WorkspaceInput):
    upstream_state: Literal['queued', 'running', 'succeeded', 'failed', 'unknown']
    outputs: list[DiscoveredOutput] = Field(default_factory=list)
    usage: dict[str, str] = Field(default_factory=dict)
    usage_fact: UsageFact | None = None
    actual_parameters: dict[str, str | int | bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    failure_reason: Literal['failed', 'expired'] | None = None

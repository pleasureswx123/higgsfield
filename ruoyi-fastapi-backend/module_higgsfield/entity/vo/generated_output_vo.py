"""适配器归一化输出，禁止把上游任意响应作为元数据写入。"""

from typing import Literal
from pydantic import Field, StrictInt, SecretStr, AwareDatetime, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput
from utils.output_source_util import validate_output_source


class OutputMetadata(WorkspaceInput):
    width: StrictInt | None = Field(default=None, gt=0, le=2147483647)
    height: StrictInt | None = Field(default=None, gt=0, le=2147483647)
    duration_seconds: str | None = Field(default=None, pattern=r'^(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$')
    format: str | None = Field(default=None, max_length=32, pattern=r'^[a-zA-Z0-9.+_-]+$')
    revised_prompt: str | None = Field(default=None, max_length=50000)


class DiscoveredOutput(WorkspaceInput):
    ordinal: StrictInt = Field(ge=0, le=2147483647)
    kind: Literal['image', 'video', 'text']
    text: str | None = Field(default=None, min_length=1, max_length=1000000)
    source_url: SecretStr | None = Field(default=None, repr=False)
    source_expires_time: AwareDatetime | None = None
    actual_metadata: OutputMetadata = Field(default_factory=OutputMetadata)

    @model_validator(mode='after')
    def content_shape(self):
        if self.kind == 'text':
            if self.text is None or self.source_url is not None or self.source_expires_time is not None:
                raise ValueError('文本输出必须有正文且不能包含下载地址')
        else:
            if self.text is not None or self.source_url is None:
                raise ValueError('媒体输出必须提供临时下载地址且不能包含文本正文')
            validate_output_source(self.source_url.get_secret_value())
        return self

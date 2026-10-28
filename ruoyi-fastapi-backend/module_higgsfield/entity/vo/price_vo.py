"""价格簿输入只接受明确用途与币种，不隐式选择采购账号。"""

from typing import Literal
from datetime import timezone
from urllib.parse import urlsplit
from pydantic import AwareDatetime, Field, model_validator, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class PriceBookCreate(WorkspaceInput):
    model_variant_id: BigId
    purpose: Literal['platform', 'procurement']
    account_id: BigId | None = None
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('价格簿名称不能为空')
        return value.strip()

    @model_validator(mode='after')
    def scope(self):
        if (self.purpose == 'procurement') != (self.account_id is not None):
            raise ValueError('采购价必须指定账号，平台价不能指定账号')
        return self


class PriceBookQuery(WorkspaceInput):
    model_variant_id: BigId | None = None
    purpose: Literal['platform', 'procurement'] | None = None
    account_id: BigId | None = None
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


class PriceSourceCreate(WorkspaceInput):
    source_type: Literal['vendor_document', 'official_screenshot', 'manual_confirmation']
    source_url: str | None = Field(default=None, max_length=4000)
    excerpt: str = Field(min_length=1, max_length=20000)
    upload_id: BigId | None = None
    observed_at: AwareDatetime

    @field_validator('excerpt')
    @classmethod
    def nonblank_excerpt(cls, value):
        if not value.strip():
            raise ValueError('来源摘录不能为空')
        return value.strip()

    @field_validator('source_url')
    @classmethod
    def safe_url(cls, value):
        if value is not None:
            url = urlsplit(value)
            if (
                url.scheme not in ('https', 'http')
                or not url.hostname
                or url.username
                or url.password
                or any(ord(c) < 33 for c in value)
            ):
                raise ValueError('出处地址必须为不含凭据和空白的 HTTP/HTTPS URL')
        return value

    @field_validator('observed_at')
    @classmethod
    def utc_time(cls, value):
        value = value.astimezone(timezone.utc)
        if value.microsecond % 1000:
            raise ValueError('获取时间最多支持毫秒精度')
        return value

    @model_validator(mode='after')
    def evidence_locator(self):
        if self.source_type != 'manual_confirmation' and not self.source_url and not self.upload_id:
            raise ValueError('文档或截图来源须提供出处地址或受控附件')
        return self

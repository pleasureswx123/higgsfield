"""汇率输入精度不得依赖数据库截断。"""

from datetime import timezone
from decimal import Decimal
from pydantic import AwareDatetime, Field, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId
from module_higgsfield.entity.vo.price_publish_vo import PriceScheduleInput


class ExchangeRateCreate(WorkspaceInput):
    base_currency: str = Field(pattern=r'^[A-Z]{3}$')
    quote_currency: str = Field(pattern=r'^[A-Z]{3}$')
    rate: str = Field(pattern=r'^(0|[1-9][0-9]{0,11})(\.[0-9]{1,12})?$')
    valid_from: AwareDatetime
    valid_until: AwareDatetime | None = None
    source_id: BigId

    @field_validator('valid_from', 'valid_until')
    @classmethod
    def utc_milliseconds(cls, value):
        if value is not None:
            value = value.astimezone(timezone.utc)
            if value.microsecond % 1000:
                raise ValueError('有效时间最多支持毫秒精度')
        return value

    @model_validator(mode='after')
    def valid_values(self):
        if self.base_currency == self.quote_currency or Decimal(self.rate) <= 0:
            raise ValueError('汇率币种必须不同且汇率必须大于零')
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError('结束时间必须晚于开始时间')
        return self


class ExchangeRatePublish(PriceScheduleInput):
    pass


class ExchangeRateQuery(WorkspaceInput):
    base_currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    quote_currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)

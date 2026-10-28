"""价格版本草稿输入：空数组可保存，数值精度与字段类型仍严格校验。"""

from decimal import Decimal
from typing import Literal, Annotated
from math import isfinite
from pydantic import Field, StrictInt, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId
from module_higgsfield.entity.vo.model_capability_vo import Scalar


class PriceItemInput(WorkspaceInput):
    item_code: str = Field(min_length=1, max_length=100, pattern=r'^[a-z][a-z0-9_]*$')
    unit: Literal['token', 'image', 'second', 'character']
    unit_quantity: str = Field(pattern=r'^(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$')
    unit_price: str = Field(pattern=r'^(0|[1-9][0-9]{0,13})(\.[0-9]{1,10})?$')
    quantity_from: str = Field(default='0', pattern=r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$')
    quantity_to: str | None = Field(default=None, pattern=r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$')
    formula_template: Literal['linear', 'tiered']
    free_reason: str | None = Field(default=None, max_length=4000)

    @model_validator(mode='after')
    def valid_numbers(self):
        if Decimal(self.unit_quantity) <= 0:
            raise ValueError('单价基数必须大于零')
        if self.quantity_to is not None and Decimal(self.quantity_to) <= Decimal(self.quantity_from):
            raise ValueError('阶梯上限必须大于下限')
        if Decimal(self.unit_price) == 0 and not (self.free_reason or '').strip():
            raise ValueError('零价必须提供免费依据')
        return self


class PriceVersionFields(WorkspaceInput):
    @field_validator('items', check_fields=False)
    @classmethod
    def distinct_starts(cls, values):
        if values is not None:
            keys = [(item.item_code, Decimal(item.quantity_from)) for item in values]
            if len(keys) != len(set(keys)):
                raise ValueError('同一分项不能重复登记相同阶梯起点')
        return values

    @field_validator('source_ids', check_fields=False)
    @classmethod
    def distinct_sources(cls, values):
        if values is not None and len(values) != len(set(values)):
            raise ValueError('价格来源不能重复')
        return values


class PriceVersionCreate(PriceVersionFields):
    price_book_id: BigId
    rounding_mode: Literal['half_up']
    calculation_scale: StrictInt = Field(ge=0, le=10)
    items: list[PriceItemInput] = Field(max_length=1000)
    source_ids: list[BigId] = Field(max_length=100)


class PriceVersionPatch(PriceVersionFields):
    revision: BigId
    rounding_mode: Literal['half_up'] | None = None
    calculation_scale: StrictInt | None = Field(default=None, ge=0, le=10)
    items: list[PriceItemInput] | None = Field(default=None, max_length=1000)
    source_ids: list[BigId] | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def meaningful_patch(self):
        fields = self.model_fields_set - {'revision'}
        if not fields or any(getattr(self, name) is None for name in fields):
            raise ValueError('至少提供一个修改字段，字段不能为 null')
        return self


class PriceVersionQuery(WorkspaceInput):
    price_book_id: BigId | None = None
    status: Literal['draft', 'published'] | None = None
    page_num: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


UsageCount = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$')]
UsageSeconds = Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,17})(\.[0-9]{1,6})?$')]


class SimulationUsage(WorkspaceInput):
    input_tokens: UsageCount | None = None
    output_tokens: UsageCount | None = None
    video_tokens: UsageCount | None = None
    characters: UsageCount | None = None
    image_count: StrictInt | None = Field(default=None, ge=0, le=2147483647)
    output_seconds: UsageSeconds | None = None
    reference_seconds: UsageSeconds | None = None

    @model_validator(mode='after')
    def valid_present_values(self):
        for name in self.model_fields_set:
            value = getattr(self, name)
            if value is None:
                raise ValueError('已提供用量不能为 null；未知用量请省略')
            if (
                name in ('input_tokens', 'output_tokens', 'video_tokens', 'characters')
                and int(value) > 9223372036854775807
            ):
                raise ValueError('整数用量超出 bigint 范围')
        return self


class PriceSimulation(WorkspaceInput):
    dimensions: dict[str, Scalar] = Field(max_length=100)
    usage: SimulationUsage
    exchange_rate_version_id: BigId | None = None

    @field_validator('dimensions')
    @classmethod
    def finite_dimensions(cls, values):
        if any(
            not key
            or len(key) > 100
            or (isinstance(value, str) and len(value) > 1000)
            or (isinstance(value, float) and not isfinite(value))
            for key, value in values.items()
        ):
            raise ValueError('规格维度含非法名称、超长字符串或非有限数值')
        return values

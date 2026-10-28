"""费用调整输入保留十进制文本，不允许零额、浮点和隐式精度截断。"""

from decimal import Decimal
from typing import Annotated
from pydantic import Field, field_validator
from module_higgsfield.entity.vo.budget_period_vo import BudgetReason
from module_higgsfield.entity.vo.project_workspace_vo import BigId


class BillingAdjustmentInput(BudgetReason):
    revision: BigId
    delta_amount: Annotated[str, Field(pattern=r'^-?(0|[1-9][0-9]{0,13})(\.[0-9]{1,10})?$')]
    usage_record_id: BigId | None = None
    reconciliation_line_id: BigId | None = None

    @field_validator('delta_amount')
    @classmethod
    def nonzero(cls, value):
        if Decimal(value) == 0:
            raise ValueError('费用调整金额不能为零')
        return value

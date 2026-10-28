"""生成入口运行时业务策略，不从客户端接收或默认猜测币种。"""

from typing import Literal

from pydantic import Field

from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class GenerationPolicy(WorkspaceInput):
    platform_currency: str = Field(pattern=r'^[A-Z]{3}$')
    procurement_currency: str = Field(pattern=r'^[A-Z]{3}$')
    missing_budget_policy: Literal['allow', 'reject']

    def currencies(self) -> dict[str, str]:
        return {'platform': self.platform_currency, 'procurement': self.procurement_currency}

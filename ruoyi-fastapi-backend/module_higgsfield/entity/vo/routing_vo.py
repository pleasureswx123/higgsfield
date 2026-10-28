"""整组路由输入；不接受通配模型、跨账号候选或隐式默认路由。"""

from pydantic import Field, StrictBool, StrictInt, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class RouteCredential(WorkspaceInput):
    credential_id: BigId
    priority: StrictInt = Field(default=100, ge=0, le=2147483647)
    max_concurrency: StrictInt = Field(ge=1, le=2147483647)


class RouteInput(WorkspaceInput):
    model_id: BigId
    account_id: BigId
    priority: StrictInt = Field(default=100, ge=0, le=2147483647)
    enabled: StrictBool
    credentials: list[RouteCredential] = Field(max_length=100)

    @model_validator(mode='after')
    def unique_credentials(self):
        ids = [item.credential_id for item in self.credentials]
        if len(ids) != len(set(ids)):
            raise ValueError('同一路由不能重复指定凭据')
        if self.enabled and not ids:
            raise ValueError('启用路由必须指定候选凭据')
        return self


class RoutingUpdate(WorkspaceInput):
    revision: BigId
    routes: list[RouteInput] = Field(max_length=200)

    @model_validator(mode='after')
    def unique_routes(self):
        identities = [(item.model_id, item.account_id) for item in self.routes]
        if len(identities) != len(set(identities)):
            raise ValueError('模型和账号组合不能重复')
        return self

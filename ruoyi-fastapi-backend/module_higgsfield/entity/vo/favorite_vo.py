"""收藏目标只能选一种，用户身份必须从登录上下文取得。"""
from typing import Literal
from pydantic import Field, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class FavoriteTarget(WorkspaceInput):
    element_id: BigId | None = None
    asset_id: BigId | None = None
    output_id: BigId | None = None

    @model_validator(mode='after')
    def exactly_one(self):
        if sum(value is not None for value in (self.element_id, self.asset_id, self.output_id)) != 1:
            raise ValueError('收藏必须指定且仅指定一个目标')
        return self


class FavoriteCreate(WorkspaceInput):
    target: FavoriteTarget


class FavoriteQuery(WorkspaceInput):
    kind: Literal['element', 'asset', 'output'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

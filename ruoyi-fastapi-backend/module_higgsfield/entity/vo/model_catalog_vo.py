"""制作端只读模型目录参数。"""

from typing import Literal
from pydantic import Field
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


class ModelCatalogQuery(WorkspaceInput):
    project_id: BigId
    version_id: BigId | None = None
    kind: Literal['image', 'video']
    q: str = Field(default='', max_length=100)
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

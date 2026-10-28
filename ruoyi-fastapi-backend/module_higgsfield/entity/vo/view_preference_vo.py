"""按页面分离白名单，拒绝任意对象、凭据与未知筛选。"""
from typing import Annotated, Literal
from datetime import date
from pydantic import Field, StrictBool, field_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId
from module_higgsfield.entity.vo.project_preference_vo import InitialRevision

ViewKey = Literal['projects', 'library', 'elements']
IdList = Annotated[list[BigId], Field(max_length=500)]


class ProjectViewSettings(WorkspaceInput):
    sort: Literal['created_desc', 'created_asc', 'name_asc'] = 'created_desc'
    status: Literal['active', 'paused', 'archived', 'pending_delete'] | None = None
    hidden: StrictBool = False
    pinned: StrictBool = False
    collection_id: BigId | None = None


class ContentViewSettings(WorkspaceInput):
    card_size: int = Field(default=4, strict=True, ge=1, le=8)
    split_by_date: StrictBool = False
    expanded_folder_ids: IdList = Field(default_factory=list)
    pinned_folder_ids: IdList = Field(default_factory=list)
    folder_order_ids: IdList = Field(default_factory=list)

    @field_validator('expanded_folder_ids', 'pinned_folder_ids', 'folder_order_ids')
    @classmethod
    def unique_ids(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('目录列表不能包含重复ID')
        return value


class LibraryViewSettings(ContentViewSettings):
    include_descendants: StrictBool = False
    layout: Literal['square', 'masonry'] = 'square'
    file_type: Literal['image', 'video', 'pdf', 'txt', 'md', 'html', 'docx', 'pptx'] | None = None
    activity: Literal['generated', 'uploaded', 'liked', 'downloaded'] | None = None
    dates: list[str] | None = Field(default=None, min_length=2, max_length=2)

    @field_validator('dates')
    @classmethod
    def valid_dates(cls, value):
        if value is None:
            return None
        # 保存上海自然日文本，查询时由客户端转换为含首不含尾的时间区间。
        parsed = [date.fromisoformat(item) for item in value]
        if any(item.isoformat() != raw for item, raw in zip(parsed, value)):
            raise ValueError('日期必须使用YYYY-MM-DD格式')
        if parsed[0] > parsed[1]:
            raise ValueError('结束日期不能早于开始日期')
        return value


class ElementViewSettings(ContentViewSettings):
    mine_filter: Literal['all', 'created', 'favorites'] = 'all'
    layout: Literal['grid', 'board', 'table'] = 'grid'
    category: Literal['character', 'scene', 'prop', 'other'] | None = None
    work_status: Literal['none', 'working', 'review', 'approved', 'rejected'] | None = None
    status_group: Literal['active', 'drafts'] | None = None


class ViewPreferenceUpdate(WorkspaceInput):
    project_id: BigId | None = None
    revision: InitialRevision
    settings: dict = Field(max_length=20)


def normalize_settings(view_key, settings):
    model = {'projects': ProjectViewSettings, 'library': LibraryViewSettings, 'elements': ElementViewSettings}[view_key]
    return model.model_validate(settings).model_dump(by_alias=True)

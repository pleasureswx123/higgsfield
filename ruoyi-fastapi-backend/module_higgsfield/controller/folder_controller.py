from typing import Annotated, Literal
from module_higgsfield.service.asset_lifecycle_service import AssetLifecycleService

from fastapi import Query, Request

from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import (
    Db,
    Key,
    OptionalKey,
    ProjectId,
    User,
    mutation_response,
)
from module_higgsfield.entity.vo.folder_vo import (
    FolderCopy,
    FolderCreate,
    FolderMove,
    FolderPatch,
    FolderQuery,
    FolderRestore,
)
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.element_service import ElementService
from utils.response_util import ResponseUtil

folder_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-目录'], order_num=82, dependencies=[PreAuthDependency()]
)


@folder_controller.get('/folders/{folder_id}', summary='读取目录及授权面包屑')
async def detail(request: Request, folder_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await FolderService.detail(db, user, folder_id))


@folder_controller.get('/projects/{project_id}/folders', summary='分页查询目录及搜索')
async def folders(request: Request, project_id: ProjectId, query: Annotated[FolderQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await FolderService.list(db, user, project_id, query))


@folder_controller.post('/projects/{project_id}/folders', summary='创建目录')
@Log(title='创建项目目录', business_type=BusinessType.INSERT)
async def create(request: Request, project_id: ProjectId, payload: FolderCreate, key: Key, db: Db, user: User):
    return mutation_response(
        await FolderService.mutate(db, user, 'create', payload.model_dump(by_alias=True), key, project_id=project_id)
    )


@folder_controller.patch('/folders/{folder_id}', summary='编辑目录')
@Log(title='编辑项目目录', business_type=BusinessType.UPDATE)
async def edit(
    request: Request, folder_id: ProjectId, payload: FolderPatch, db: Db, user: User, key: OptionalKey = None
):
    return mutation_response(
        await FolderService.mutate(db, user, 'edit', payload.model_dump(by_alias=True), key, folder_id=folder_id)
    )


@folder_controller.post('/folders/{folder_id}/move', summary='移动目录')
@Log(title='移动项目目录', business_type=BusinessType.UPDATE)
async def move(request: Request, folder_id: ProjectId, payload: FolderMove, key: Key, db: Db, user: User):
    return mutation_response(
        await FolderService.mutate(db, user, 'move', payload.model_dump(by_alias=True), key, folder_id=folder_id)
    )


@folder_controller.post('/folders/{folder_id}/copy', summary='复制目录树')
@Log(title='复制项目目录', business_type=BusinessType.INSERT)
async def copy(request: Request, folder_id: ProjectId, payload: FolderCopy, key: Key, db: Db, user: User):
    return mutation_response(
        await FolderService.mutate(db, user, 'copy', payload.model_dump(by_alias=True), key, folder_id=folder_id)
    )


@folder_controller.delete('/folders/{folder_id}', summary='将内容移到父级并回收目录')
@Log(title='回收项目目录', business_type=BusinessType.DELETE)
async def delete(
    request: Request,
    folder_id: ProjectId,
    db: Db,
    user: User,
    revision: Annotated[str, Query(pattern=r'^[1-9][0-9]{0,18}$')],
    mode: Literal['moveEntriesToParent'] = 'moveEntriesToParent',
    key: OptionalKey = None,
):
    return mutation_response(
        await FolderService.mutate(db, user, 'delete', {'revision': revision, 'mode': mode}, key, folder_id=folder_id)
    )


@folder_controller.post('/folders/{folder_id}/restore', summary='恢复原目录身份')
@Log(title='恢复项目目录', business_type=BusinessType.UPDATE)
async def restore(request: Request, folder_id: ProjectId, payload: FolderRestore, key: Key, db: Db, user: User):
    return mutation_response(
        await FolderService.mutate(
            db, user, 'restore', payload.model_dump(by_alias=True, exclude_unset=True), key, folder_id=folder_id
        )
    )


@folder_controller.get('/projects/{project_id}/trash', summary='项目内容回收站')
async def trash(
    request: Request,
    project_id: ProjectId,
    db: Db,
    user: User,
    pageNum: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100)] = 30,
    kind: Literal['folder', 'element', 'asset'] = 'folder',
):
    service = {'element': ElementService, 'folder': FolderService, 'asset': AssetLifecycleService}[kind]
    return ResponseUtil.success(model_content=await service.trash(db, user, project_id, pageNum, pageSize))


@folder_controller.get('/projects/{project_id}/folder-asset-counts', summary='读取未删除素材总数及目录直接素材数')
async def asset_counts(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await FolderService.asset_counts(db, user, project_id))

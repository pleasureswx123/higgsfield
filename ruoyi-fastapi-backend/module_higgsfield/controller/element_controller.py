from typing import Annotated

from fastapi import Query, Request
from common.annotation.log_annotation import Log
from common.aspect.pre_auth import PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import (
    Db,
    Key,
    OptionalKey,
    ProjectId,
    User,
    mutation_response,
)
from module_higgsfield.entity.vo.element_vo import (
    ElementCreate,
    ElementCopy,
    ElementLabel,
    ElementMove,
    ElementPatch,
    ElementQuery,
    ElementRevisionCreate,
    ElementRevisionAction,
    ElementSave,
    PropertyDefinitionCreate,
    PropertyDefinitionFields,
)
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.element_copy_service import ElementCopyService
from utils.response_util import ResponseUtil

element_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-元素'], order_num=84, dependencies=[PreAuthDependency()]
)
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@element_controller.post('/elements/{element_id}/copy', summary='双向授权复制元素固定修订')
@Log(title='受控复制项目元素', business_type=BusinessType.INSERT)
async def copy_element(request: Request, element_id: ProjectId, payload: ElementCopy, key: Key, db: Db, user: User):
    return mutation_response(await ElementCopyService.copy(db, user, element_id, payload, key))


@element_controller.delete('/elements/{element_id}', summary='逻辑删除元素并记录恢复期限')
@Log(title='回收项目元素', business_type=BusinessType.DELETE)
async def delete_element(
    request: Request,
    element_id: ProjectId,
    query: Annotated[ElementRevisionAction, Query()],
    db: Db,
    user: User,
    key: OptionalKey = None,
):
    return mutation_response(await ElementService.lifecycle(db, user, element_id, 'delete', query, key))


@element_controller.post('/elements/{element_id}/restore', summary='恢复元素原身份与固定修订')
@Log(title='恢复项目元素', business_type=BusinessType.UPDATE)
async def restore_element(
    request: Request, element_id: ProjectId, payload: ElementRevisionAction, key: Key, db: Db, user: User
):
    return mutation_response(await ElementService.lifecycle(db, user, element_id, 'restore', payload, key))


@element_controller.patch('/element-revisions/{revision_id}/label', summary='修改修订展示标签')
@Log(title='修改元素修订标签', business_type=BusinessType.UPDATE)
async def revision_label(
    request: Request, revision_id: ProjectId, payload: ElementLabel, db: Db, user: User, key: OptionalKey = None
):
    return mutation_response(await ElementService.label(db, user, revision_id, payload, key))


@element_controller.get('/elements', summary='分页读取有权访问的元素')
async def elements(request: Request, query: Annotated[ElementQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ElementService.listing(db, user, query))


@element_controller.post('/elements', summary='原子创建元素身份与首个修订')
@Log(title='创建项目元素', business_type=BusinessType.INSERT)
async def create_element(request: Request, payload: ElementCreate, key: Key, db: Db, user: User):
    return mutation_response(await ElementService.create(db, user, payload, key))


@element_controller.get('/elements/{element_id}', summary='读取元素与当前固定修订')
async def element_detail(request: Request, element_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ElementService.detail(db, user, element_id))


@element_controller.patch('/elements/{element_id}', summary='修改元素身份字段')
@Log(title='编辑元素身份', business_type=BusinessType.UPDATE)
async def patch_element(
    request: Request, element_id: ProjectId, payload: ElementPatch, db: Db, user: User, key: OptionalKey = None
):
    return mutation_response(await ElementService.mutate(db, user, element_id, 'patch', payload, key))


@element_controller.post('/elements/{element_id}/save', summary='原子保存元素身份与内容')
@Log(title='保存项目元素', business_type=BusinessType.UPDATE)
async def save_element(request: Request, element_id: ProjectId, payload: ElementSave, key: Key, db: Db, user: User):
    return mutation_response(await ElementService.mutate(db, user, element_id, 'save', payload, key))


@element_controller.post('/elements/{element_id}/move', summary='移动元素目录归属')
@Log(title='移动项目元素', business_type=BusinessType.UPDATE)
async def move_element(request: Request, element_id: ProjectId, payload: ElementMove, key: Key, db: Db, user: User):
    return mutation_response(await ElementService.mutate(db, user, element_id, 'move', payload, key))


@element_controller.post('/elements/{element_id}/revisions', summary='保存元素固定资料修订')
@Log(title='新增元素修订', business_type=BusinessType.INSERT)
async def add_revision(
    request: Request, element_id: ProjectId, payload: ElementRevisionCreate, key: Key, db: Db, user: User
):
    return mutation_response(await ElementService.mutate(db, user, element_id, 'revisions', payload, key))


@element_controller.get('/elements/{element_id}/revisions', summary='分页读取元素历史修订')
async def element_revisions(
    request: Request, element_id: ProjectId, db: Db, user: User, pageNum: PageNumber = 1, pageSize: PageSize = 30
):
    return ResponseUtil.success(model_content=await ElementService.revisions(db, user, element_id, pageNum, pageSize))


@element_controller.get('/projects/{project_id}/property-definitions', summary='读取项目最新属性定义')
async def property_definitions(
    request: Request, project_id: ProjectId, db: Db, user: User, pageNum: PageNumber = 1, pageSize: PageSize = 30
):
    return ResponseUtil.success(model_content=await ElementService.definitions(db, user, project_id, pageNum, pageSize))


@element_controller.post('/projects/{project_id}/property-definitions', summary='创建项目属性定义')
@Log(title='创建元素属性', business_type=BusinessType.INSERT)
async def create_property(
    request: Request, project_id: ProjectId, payload: PropertyDefinitionCreate, key: Key, db: Db, user: User
):
    return mutation_response(await ElementService.write_definition(db, user, payload, key, project_id=project_id))


@element_controller.post('/property-definitions/{definition_id}/versions', summary='追加属性定义不可变版本')
@Log(title='新增属性定义版本', business_type=BusinessType.INSERT)
async def property_version(
    request: Request, definition_id: ProjectId, payload: PropertyDefinitionFields, key: Key, db: Db, user: User
):
    return mutation_response(await ElementService.write_definition(db, user, payload, key, definition_id=definition_id))

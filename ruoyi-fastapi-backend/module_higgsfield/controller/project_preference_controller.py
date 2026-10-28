"""个人项目集合与偏好接口。"""
from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.project_preference_vo import CollectionCreate, CollectionUpdate, CollectionQuery, PreferenceUpdate
from module_higgsfield.entity.vo.project_workspace_vo import BigId
from module_higgsfield.service.project_preference_service import PreferenceService
from utils.response_util import ResponseUtil

project_preference_controller = APIRouterPro(prefix='/api/v1', tags=['制作平台-个人项目导航'],
    order_num=88, dependencies=[PreAuthDependency()])


@project_preference_controller.get('/project-collections', summary='本人项目集合')
async def collections(request: Request, query: Annotated[CollectionQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await PreferenceService.list_collections(db, user, query))


@project_preference_controller.post('/project-collections', summary='创建个人集合')
async def create(request: Request, payload: CollectionCreate, key: Key, db: Db, user: User):
    return mutation_response(await PreferenceService.mutate_collection(db, user, 'create', payload.model_dump(by_alias=True), key))


@project_preference_controller.patch('/project-collections/{identity}', summary='修改个人集合')
async def update(request: Request, identity: ProjectId, payload: CollectionUpdate, key: Key, db: Db, user: User):
    return mutation_response(await PreferenceService.mutate_collection(db, user, 'update',
        payload.model_dump(by_alias=True, exclude_unset=True), key, identity))


@project_preference_controller.delete('/project-collections/{identity}', summary='解除个人集合分组')
async def delete(request: Request, identity: ProjectId, revision: Annotated[BigId, Query()], key: Key, db: Db, user: User):
    return mutation_response(await PreferenceService.mutate_collection(db, user, 'delete', {'revision': revision}, key, identity))


@project_preference_controller.get('/projects/{project_id}/preferences', summary='读取本人项目偏好')
async def preference(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await PreferenceService.get_preference(db, user, project_id))


@project_preference_controller.put('/projects/{project_id}/preferences', summary='保存本人项目偏好')
async def put(request: Request, project_id: ProjectId, payload: PreferenceUpdate, key: Key, db: Db, user: User):
    return mutation_response(await PreferenceService.put_preference(db, user, project_id,
        payload.model_dump(by_alias=True, exclude_unset=True), key))

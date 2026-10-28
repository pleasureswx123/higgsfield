"""页面偏好仅允许当前用户读取与保存。"""
from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, mutation_response
from module_higgsfield.entity.vo.project_workspace_vo import BigId
from module_higgsfield.entity.vo.view_preference_vo import ViewKey, ViewPreferenceUpdate
from module_higgsfield.service.view_preference_service import ViewPreferenceService
from utils.response_util import ResponseUtil

view_preference_controller = APIRouterPro(prefix='/api/v1/view-preferences', tags=['制作平台-视图偏好'],
    order_num=89, dependencies=[PreAuthDependency()])


@view_preference_controller.get('/{view_key}', summary='读取本人视图偏好')
async def get(request: Request, view_key: ViewKey, db: Db, user: User,
              project_id: Annotated[BigId | None, Query(alias='projectId')] = None):
    return ResponseUtil.success(data=await ViewPreferenceService.get(db, user, view_key, int(project_id) if project_id else None))


@view_preference_controller.put('/{view_key}', summary='保存本人视图偏好')
async def put(request: Request, view_key: ViewKey, payload: ViewPreferenceUpdate, key: Key, db: Db, user: User):
    return mutation_response(await ViewPreferenceService.put(db, user, view_key, payload, key))

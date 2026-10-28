"""后台加入申请审批，成员权限和对象授权在Service逐次核验。"""
from typing import Annotated
from fastapi import Query, Request
from common.router import APIRouterPro
from common.aspect.pre_auth import PreAuthDependency
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.project_join_vo import JoinQuery, JoinReview
from module_higgsfield.service.project_join_service import ProjectJoinService
from utils.response_util import ResponseUtil

project_join_controller = APIRouterPro(prefix='/api/admin/v1', tags=['制作平台后台-加入申请'],
    order_num=87, dependencies=[PreAuthDependency()])


@project_join_controller.get('/projects/{project_id}/join-requests', summary='分页读取授权项目的加入申请')
async def listing(request: Request, project_id: ProjectId, query: Annotated[JoinQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ProjectJoinService.listing(db, user, project_id, query))


@project_join_controller.post('/join-requests/{identity}/review', summary='审批加入申请并原子授予成员身份')
async def review(request: Request, identity: ProjectId, payload: JoinReview, key: Key, db: Db, user: User):
    return mutation_response(await ProjectJoinService.review(db, user, identity, payload, key))

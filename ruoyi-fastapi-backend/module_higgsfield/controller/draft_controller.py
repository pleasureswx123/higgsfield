from typing import Annotated
from fastapi import Request, Query
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.draft_vo import DraftCreate, DraftUpdate, DraftQuery
from module_higgsfield.service.draft_service import DraftService
from utils.response_util import ResponseUtil

draft_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-私有草稿'], order_num=86, dependencies=[PreAuthDependency()]
)


@draft_controller.get('/drafts', summary='分页读取当前项目下本人私有草稿摘要')
async def listing(request: Request, query: Annotated[DraftQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await DraftService.listing(db, user, query))


@draft_controller.post('/drafts', summary='创建本人私有生成草稿')
async def create(request: Request, payload: DraftCreate, key: Key, db: Db, user: User):
    return mutation_response(await DraftService.save(db, user, payload, key))


@draft_controller.get('/drafts/{draft_id}', summary='读取本人私有生成草稿')
async def get(request: Request, draft_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await DraftService.get(db, user, draft_id))


@draft_controller.put('/drafts/{draft_id}', summary='按并发版本保存本人草稿')
async def save(request: Request, draft_id: ProjectId, payload: DraftUpdate, key: Key, db: Db, user: User):
    return mutation_response(await DraftService.save(db, user, payload, key, draft_id))

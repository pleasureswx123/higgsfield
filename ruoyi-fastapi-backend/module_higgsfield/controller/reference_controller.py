from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User
from module_higgsfield.entity.vo.reference_vo import ReferenceQuery, ReferenceUpdatesQuery
from module_higgsfield.service.reference_update_service import ReferenceUpdateService
from module_higgsfield.service.reference_service import ReferenceService
from utils.response_util import ResponseUtil

reference_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-生成引用'], order_num=85, dependencies=[PreAuthDependency()]
)


@reference_controller.get('/references/search', summary='检索当前项目授权引用候选')
async def search(request: Request, query: Annotated[ReferenceQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ReferenceService.search(db, user, query))


@reference_controller.post('/references/updates', summary='检查固定元素引用是否存在可用的新修订，不修改草稿')
async def updates(request: Request, payload: ReferenceUpdatesQuery, db: Db, user: User):
    return ResponseUtil.success(data=await ReferenceUpdateService.check(db, user, payload))

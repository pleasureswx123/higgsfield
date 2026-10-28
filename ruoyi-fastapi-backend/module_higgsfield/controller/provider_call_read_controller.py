from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId
from module_higgsfield.entity.vo.provider_call_query_vo import ProviderCallQuery
from module_higgsfield.service.provider_call_read_service import ProviderCallReadService
from utils.response_util import ResponseUtil

provider_call_read_controller = APIRouterPro(
    prefix='/api/admin/v1/provider-calls', tags=['后台管理-供应商调用'], order_num=96,
    dependencies=[PreAuthDependency()],
)


@provider_call_read_controller.get('', summary='分页读取管理范围内的调用事实')
async def listing(request: Request, query: Annotated[ProviderCallQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ProviderCallReadService.listing(db, user, query))


@provider_call_read_controller.get('/{call_id}', summary='读取脱敏调用证据')
async def detail(request: Request, call_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ProviderCallReadService.detail(db, user, call_id))

from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.provider_vo import ConnectionCreate, ConnectionPatch, ConnectionQuery
from module_higgsfield.service.provider_service import ProviderService
from module_higgsfield.entity.vo.provider_vo import ProviderAccountCreate, ProviderAccountQuery
from utils.response_util import ResponseUtil

provider_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-供应商连接'], order_num=88, dependencies=[PreAuthDependency()]
)


@provider_controller.get('/provider-connections', summary='分页读取供应商连接')
async def listing(request: Request, query: Annotated[ConnectionQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ProviderService.listing(db, user, query))


@provider_controller.get('/provider-connections/{connection_id}', summary='读取供应商连接非秘密配置')
async def get(request: Request, connection_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ProviderService.get(db, user, connection_id))


@provider_controller.post('/provider-connections', summary='登记草稿连接与首个配置版本')
@Log(title='登记供应商连接', business_type=BusinessType.INSERT)
async def create(request: Request, payload: ConnectionCreate, key: Key, db: Db, user: User):
    return mutation_response(await ProviderService.save(db, user, payload, key))


@provider_controller.patch('/provider-connections/{connection_id}', summary='创建连接新配置并保留历史版本')
@Log(title='更新供应商连接', business_type=BusinessType.UPDATE)
async def update(request: Request, connection_id: ProjectId, payload: ConnectionPatch, key: Key, db: Db, user: User):
    return mutation_response(await ProviderService.save(db, user, payload, key, connection_id))


@provider_controller.get('/provider-accounts', summary='分页读取供应商账号作用域')
async def accounts(request: Request, query: Annotated[ProviderAccountQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ProviderService.accounts(db, user, query))


@provider_controller.post('/provider-accounts', summary='登记供应商账号及上游项目')
@Log(title='登记供应商账号', business_type=BusinessType.INSERT)
async def create_account(request: Request, payload: ProviderAccountCreate, key: Key, db: Db, user: User):
    return mutation_response(await ProviderService.create_account(db, user, payload, key))

"""凭据管理接口；写请求及响应不进入通用操作日志。"""

from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.credential_route import CredentialRoute
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.credential_vo import (
    CredentialCreate,
    CredentialVersionCreate,
    CredentialPage,
    CredentialQuery,
)
from module_higgsfield.service.credential_service import CredentialService
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.credential_vo import CredentialStateAction
from module_higgsfield.service.credential_state_service import CredentialStateService
from module_higgsfield.entity.vo.credential_vo import CredentialActivate
from module_higgsfield.service.credential_activation_service import CredentialActivationService


credential_controller = APIRouterPro(
    prefix='/api/admin/v1',
    tags=['后台管理-供应商凭据'],
    order_num=89,
    dependencies=[PreAuthDependency()],
    route_class=CredentialRoute,
)


@credential_controller.get('/credentials', summary='分页查询凭据身份')
async def listing(request: Request, query: Annotated[CredentialQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await CredentialService.listing(db, user, query))


@credential_controller.get('/credentials/{credential_id}', summary='读取凭据非秘密元数据')
async def get(request: Request, credential_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await CredentialService.get(db, user, credential_id))


@credential_controller.get('/credentials/{credential_id}/versions', summary='分页读取脱敏凭据版本')
async def versions(
    request: Request, credential_id: ProjectId, query: Annotated[CredentialPage, Query()], db: Db, user: User
):
    return ResponseUtil.success(model_content=await CredentialService.listing(db, user, query, credential_id))


@credential_controller.post('/credentials', summary='登记凭据与首个加密草稿版本')
@Log(title='登记供应商凭据', business_type=BusinessType.INSERT, request_log_mode='none', response_log_mode='none')
async def create(request: Request, payload: CredentialCreate, key: Key, db: Db, user: User):
    return mutation_response(await CredentialService.save(db, user, payload, key))


@credential_controller.post('/credentials/{credential_id}/versions', summary='创建凭据轮换草稿，保留旧版本')
@Log(title='轮换供应商凭据', business_type=BusinessType.INSERT, request_log_mode='none', response_log_mode='none')
async def rotate(
    request: Request, credential_id: ProjectId, payload: CredentialVersionCreate, key: Key, db: Db, user: User
):
    return mutation_response(await CredentialService.save(db, user, payload, key, credential_id))


@credential_controller.post('/credential-versions/{version_id}/drain', summary='排空凭据版本，保留在途依赖')
@Log(title='排空凭据版本', business_type=BusinessType.UPDATE, request_log_mode='none', response_log_mode='none')
async def drain(request: Request, version_id: ProjectId, payload: CredentialStateAction, key: Key, db: Db, user: User):
    return mutation_response(await CredentialStateService.mutate(db, user, version_id, 'drain', payload, key))


@credential_controller.post('/credential-versions/{version_id}/disable', summary='无在途任务后停用凭据版本')
@Log(title='停用凭据版本', business_type=BusinessType.UPDATE, request_log_mode='none', response_log_mode='none')
async def disable(
    request: Request, version_id: ProjectId, payload: CredentialStateAction, key: Key, db: Db, user: User
):
    return mutation_response(await CredentialStateService.mutate(db, user, version_id, 'disable', payload, key))


@credential_controller.post(
    '/credential-versions/{version_id}/revoke', summary='本地紧急撤销凭据版本，不认定上游已停止'
)
@Log(title='撤销凭据版本', business_type=BusinessType.UPDATE, request_log_mode='none', response_log_mode='none')
async def revoke(request: Request, version_id: ProjectId, payload: CredentialStateAction, key: Key, db: Db, user: User):
    return mutation_response(await CredentialStateService.mutate(db, user, version_id, 'revoke', payload, key))


@credential_controller.post('/credential-versions/{version_id}/activate', summary='依据当前配置的成功测试启用草稿凭据')
@Log(title='启用凭据版本', business_type=BusinessType.UPDATE, request_log_mode='none', response_log_mode='none')
async def activate(request: Request, version_id: ProjectId, payload: CredentialActivate, key: Key, db: Db, user: User):
    return mutation_response(await CredentialActivationService.activate(db, user, version_id, payload, key))

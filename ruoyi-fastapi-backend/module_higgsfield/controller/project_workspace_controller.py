from typing import Annotated

from fastapi import Header, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_session import DBSessionDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.entity.vo.project_workspace_vo import BriefUpdate, MemberAdd, MemberQuery, MemberUpdate
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.project_permission_service import ProjectPermissionService
from module_higgsfield.entity.vo.project_workspace_vo import ProjectPermissionUpdate, OwnershipTransfer
from module_higgsfield.service.project_ownership_service import ProjectOwnershipService
from utils.response_util import ResponseUtil

project_workspace_controller = APIRouterPro(
    prefix='/api/v1/projects', tags=['制作平台-简报与成员'], order_num=81, dependencies=[PreAuthDependency()]
)
Db = Annotated[AsyncSession, DBSessionDependency()]
User = Annotated[CurrentUserModel, CurrentUserDependency()]
ProjectId = Annotated[int, Path(gt=0, le=9223372036854775807)]
Key = Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')]
OptionalKey = Annotated[str | None, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')]


def mutation_response(result):
    body, replayed = result
    return JSONResponse(content=body, headers={'Idempotent-Replayed': 'true'} if replayed else None)


@project_workspace_controller.get('/{project_id}/brief', summary='读取项目简报')
async def brief(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await WorkspaceService.get_brief(db, user, project_id))


@project_workspace_controller.put('/{project_id}/brief', summary='保存项目简报')
@Log(title='编辑项目简报', business_type=BusinessType.UPDATE)
async def update_brief(
    request: Request, project_id: ProjectId, payload: BriefUpdate, db: Db, user: User, key: OptionalKey = None
):
    return mutation_response(
        await WorkspaceService.mutate(db, user, project_id, 'brief', payload.model_dump(by_alias=True), key)
    )


@project_workspace_controller.get('/{project_id}/members', summary='项目成员列表')
async def members(request: Request, project_id: ProjectId, query: Annotated[MemberQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await WorkspaceService.list_members(db, user, project_id, query))


@project_workspace_controller.get('/{project_id}/roles', summary='项目角色与可授予范围')
async def roles(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await WorkspaceService.roles(db, user, project_id))


@project_workspace_controller.get('/{project_id}/member-candidates', summary='精确账号查找可添加成员')
async def candidates(
    request: Request,
    project_id: ProjectId,
    db: Db,
    user: User,
    account: Annotated[str, Query(min_length=1, max_length=30)],
):
    return ResponseUtil.success(data=await WorkspaceService.candidate(db, user, project_id, account))


@project_workspace_controller.post('/{project_id}/members', summary='添加或恢复项目成员')
@Log(title='添加项目成员', business_type=BusinessType.INSERT)
async def add_member(request: Request, project_id: ProjectId, payload: MemberAdd, key: Key, db: Db, user: User):
    return mutation_response(
        await WorkspaceService.mutate(db, user, project_id, 'add', payload.model_dump(by_alias=True), key)
    )


@project_workspace_controller.patch('/{project_id}/members/{user_id}', summary='调整项目成员角色')
@Log(title='调整项目成员角色', business_type=BusinessType.UPDATE)
async def update_member(
    request: Request,
    project_id: ProjectId,
    user_id: ProjectId,
    payload: MemberUpdate,
    db: Db,
    user: User,
    key: OptionalKey = None,
):
    return mutation_response(
        await WorkspaceService.mutate(db, user, project_id, 'role', payload.model_dump(by_alias=True), key, user_id)
    )


@project_workspace_controller.delete('/{project_id}/members/{user_id}', summary='移除项目成员并保留身份记录')
@Log(title='移除项目成员', business_type=BusinessType.DELETE)
async def remove_member(
    request: Request,
    project_id: ProjectId,
    user_id: ProjectId,
    revision: Annotated[str, Query(pattern=r'^[1-9][0-9]{0,18}$')],
    db: Db,
    user: User,
    key: OptionalKey = None,
):
    return mutation_response(
        await WorkspaceService.mutate(db, user, project_id, 'remove', {'revision': revision}, key, user_id)
    )


@project_workspace_controller.get('/{project_id}/role-permissions', summary='读取项目角色权限矩阵')
async def role_permissions(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ProjectPermissionService.read(db, user, project_id))


@project_workspace_controller.put('/{project_id}/role-permissions', summary='保存当前项目角色权限')
@Log(title='配置项目角色权限', business_type=BusinessType.UPDATE)
async def save_role_permissions(request: Request, project_id: ProjectId, payload: ProjectPermissionUpdate, key: Key, db: Db, user: User):
    return mutation_response(await ProjectPermissionService.save(db, user, project_id, payload, key))


@project_workspace_controller.put('/{project_id}/ownership', summary='转让项目所有权')
@Log(title='转让项目所有权', business_type=BusinessType.UPDATE)
async def transfer_ownership(request: Request, project_id: ProjectId, payload: OwnershipTransfer, key: Key, db: Db, user: User):
    return mutation_response(await ProjectOwnershipService.transfer(db, user, project_id, payload, key))

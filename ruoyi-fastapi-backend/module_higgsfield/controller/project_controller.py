from typing import Annotated

from fastapi import Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.log_annotation import Log
from common.aspect.db_session import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.enums import BusinessType
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.entity.vo.project_vo import ProjectCreate, ProjectModel, ProjectQuery, ProjectArchive, ProjectRestore, ProjectUpdate, ProjectPause
from module_higgsfield.service.project_lifecycle_service import ProjectLifecycleService
from module_higgsfield.service.project_service import ProjectService
from utils.response_util import ResponseUtil

project_controller = APIRouterPro(
    prefix='/api/v1/projects', tags=['制作平台-项目'], order_num=80, dependencies=[PreAuthDependency()]
)


@project_controller.get(
    '',
    response_model=PageResponseModel[ProjectModel],
    summary='我的项目列表',
    dependencies=[UserInterfaceAuthDependency('project:read')],
)
async def list_projects(
    request: Request,
    query: Annotated[ProjectQuery, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ProjectService.list_projects(db, user, query)
    return ResponseUtil.success(model_content=result)


@project_controller.post(
    '',
    response_model=DataResponseModel[ProjectModel],
    summary='新建项目',
    dependencies=[UserInterfaceAuthDependency('project:create')],
)
@Log(title='制作平台新建项目', business_type=BusinessType.INSERT)
async def create_project(
    request: Request,
    payload: ProjectCreate,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectService.create_project(db, user, payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)


@project_controller.get(
    '/{project_id}',
    response_model=DataResponseModel[ProjectModel],
    summary='项目详情',
    dependencies=[UserInterfaceAuthDependency('project:read')],
)
async def project_detail(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ProjectService.get_project(db, user, project_id)
    return ResponseUtil.success(data=result.model_dump(by_alias=True))


@project_controller.post('/{project_id}/archive', response_model=DataResponseModel[ProjectModel],
    summary='归档项目')
@Log(title='制作平台归档项目', business_type=BusinessType.UPDATE)
async def archive_project(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    payload: ProjectArchive,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectLifecycleService.change(db, user, project_id, 'archive', payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)


@project_controller.post('/{project_id}/restore', response_model=DataResponseModel[ProjectModel],
    summary='恢复归档项目')
@Log(title='制作平台恢复项目', business_type=BusinessType.UPDATE)
async def restore_project(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    payload: ProjectRestore,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectLifecycleService.change(db, user, project_id, 'restore', payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)

@project_controller.patch('/{project_id}', response_model=DataResponseModel[ProjectModel],
    summary='编辑项目基本信息')
@Log(title='制作平台编辑项目', business_type=BusinessType.UPDATE)
async def update_project(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    payload: ProjectUpdate,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectLifecycleService.change(db, user, project_id, 'rename', payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)

@project_controller.post('/{project_id}/pause', response_model=DataResponseModel[ProjectModel],
    summary='暂停项目')
@Log(title='制作平台暂停项目', business_type=BusinessType.UPDATE)
async def pause_project(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    payload: ProjectPause,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectLifecycleService.change(db, user, project_id, 'pause', payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)


@project_controller.post('/{project_id}/resume', response_model=DataResponseModel[ProjectModel],
    summary='恢复项目运行')
@Log(title='制作平台恢复项目运行', business_type=BusinessType.UPDATE)
async def resume_project(
    request: Request,
    project_id: Annotated[int, Path(gt=0, le=9223372036854775807)],
    payload: ProjectRestore,
    key: Annotated[str, Header(alias='Idempotency-Key', min_length=16, max_length=128, pattern=r'^[ -~]+$')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result, replayed = await ProjectLifecycleService.change(db, user, project_id, 'resume', payload, key)
    return JSONResponse(content=result, headers={'Idempotent-Replayed': 'true'} if replayed else None)


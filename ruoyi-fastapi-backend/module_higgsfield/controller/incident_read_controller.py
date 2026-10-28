from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId, Key, mutation_response
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from module_higgsfield.entity.vo.incident_action_vo import IncidentAction
from module_higgsfield.service.generation_archive_retry_service import GenerationArchiveRetryService
from module_higgsfield.service.incident_requery_service import IncidentRequeryService
from module_higgsfield.service.incident_tracking_service import IncidentTrackingService
from module_higgsfield.service.incident_rejection_service import IncidentRejectionService
from module_higgsfield.entity.vo.incident_query_vo import IncidentQuery
from module_higgsfield.service.incident_read_service import IncidentReadService
from utils.response_util import ResponseUtil

incident_read_controller = APIRouterPro(prefix='/api/admin/v1/generation-incidents',
    tags=['后台管理-异常任务'], order_num=97, dependencies=[PreAuthDependency()])


@incident_read_controller.get('', summary='分页读取管理范围内的异常任务')
async def listing(request: Request, query: Annotated[IncidentQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await IncidentReadService.listing(db, user, query))


@incident_read_controller.get('/{job_id}', summary='读取异常任务状态与脱敏证据定位')
async def detail(request: Request, job_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await IncidentReadService.detail(db, user, job_id))


@incident_read_controller.post('/{job_id}/actions', summary='重新调度状态核查或归档，不重新生成')
@Log(title='异常任务恢复', business_type=BusinessType.UPDATE)
async def action(request: Request, job_id: ProjectId, payload: IncidentAction, key: Key, db: Db, user: User):
    if payload.action == 'confirm_not_accepted':
        return mutation_response(await IncidentRejectionService.confirm(db, user, job_id, payload, key))
    if payload.action == 'close_tracking':
        return mutation_response(await IncidentTrackingService.close(db, user, job_id, payload, key))
    if payload.action == 'requery':
        return mutation_response(await IncidentRequeryService.requery(db, user, job_id, payload, key))
    return mutation_response(await GenerationArchiveRetryService.retry_managed(db, user, job_id, payload, key))

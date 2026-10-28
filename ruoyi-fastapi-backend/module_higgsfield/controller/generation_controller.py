from typing import Annotated
from fastapi import Request, Query, Header
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId
from module_higgsfield.service.generation_read_service import GenerationReadService
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.generation_query_vo import GenerationQuery
from module_higgsfield.service.task_event_service import TaskEventService
from module_higgsfield.entity.vo.generation_action_vo import GenerationCancel
from module_higgsfield.service.generation_cancel_service import GenerationCancelService
from module_higgsfield.entity.vo.generation_action_vo import GenerationRetryArchive
from module_higgsfield.service.generation_archive_retry_service import GenerationArchiveRetryService
from module_higgsfield.controller.project_workspace_controller import Key, mutation_response
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.generation_policy_service import GenerationPolicyService
from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.generation_validation_service import GenerationValidationService

generation_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-生成任务'], order_num=87, dependencies=[PreAuthDependency()]
)


@generation_controller.post('/generations/validate', summary='检查生成可受理性，不预占或发起消费')
async def validate_generation(request: Request, payload: GenerationInput, db: Db, user: User):
    return ResponseUtil.success(
        data=await GenerationValidationService.validate(
            db, user, payload, GenerationPolicyService.configured(), GenerationPolicyService.tokens()
        )
    )


@generation_controller.post('/generations', summary='原子受理任务与预算预占')
async def accept_generation(request: Request, payload: GenerationInput, key: Key, db: Db, user: User):
    policy = GenerationPolicyService.configured()
    return mutation_response(
        await GenerationAcceptService.accept(
            db, user, payload, key, currencies=policy.currencies(), missing_budget_policy=policy.missing_budget_policy
        )
    )


@generation_controller.post('/generations/{job_id}/cancel', summary='取消明确未提交的任务并释放原预占')
async def cancel(request: Request, job_id: ProjectId, payload: GenerationCancel, key: Key, db: Db, user: User):
    return mutation_response(await GenerationCancelService.cancel(db, user, job_id, payload, key))


@generation_controller.post('/generations/{job_id}/retry-archive', summary='仅重试已有失败输出的归档')
async def retry_archive(request: Request, job_id: ProjectId, payload: GenerationRetryArchive, key: Key, db: Db, user: User):
    return mutation_response(await GenerationArchiveRetryService.retry(db, user, job_id, payload, key))


@generation_controller.get('/generations', summary='分页读取当前授权范围内的生成任务')
async def listing(request: Request, query: Annotated[GenerationQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await GenerationReadService.listing(db, user, query))


@generation_controller.get('/generations/{job_id}/input', summary='读取已授权生成任务的固定输入')
async def original_input(request: Request, job_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await GenerationReadService.input(db, user, job_id))


@generation_controller.get('/generations/{job_id}', summary='读取任务聚合状态与已授权输出快照')
async def snapshot(request: Request, job_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await GenerationReadService.snapshot(db, user, job_id))


@generation_controller.get('/generations/{job_id}/events', summary='订阅任务持久事件与重放')
async def events(
    request: Request,
    job_id: ProjectId,
    db: Db,
    user: User,
    last_event_id: Annotated[str | None, Header(alias='Last-Event-ID', max_length=40)] = None,
):
    sequence = TaskEventService.cursor(job_id, last_event_id)
    frames, sequence, visibility = await TaskEventService.batch(db, user, job_id, sequence)
    await db.rollback()
    token = request.headers.get('authorization', '')
    return ResponseUtil.streaming(
        data=TaskEventService.stream(request, token, job_id, sequence, frames, visibility),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'},
    )

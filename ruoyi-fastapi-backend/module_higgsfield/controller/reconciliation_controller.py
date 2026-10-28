"""管理对账受理入口，复用平台鉴权与响应协议。"""
from typing import Annotated
from fastapi import Request, Query, Response
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.reconciliation_vo import ReconciliationCreate, ReconciliationQuery, ReconciliationLineQuery
from module_higgsfield.service.reconciliation_service import ReconciliationService
from module_higgsfield.entity.vo.reconciliation_vo import ReconciliationMatch, ReconciliationConfirm, ReconciliationResolve
from module_higgsfield.service.reconciliation_action_service import ReconciliationActionService


reconciliation_controller = APIRouterPro(prefix='/api/admin/v1', tags=['后台管理-对账'],
    order_num=101, dependencies=[PreAuthDependency()])


@reconciliation_controller.post('/reconciliations', summary='受理对账文件，尚未匹配或确认')
@Log(title='受理对账文件', business_type=BusinessType.INSERT)
async def create(request: Request, payload: ReconciliationCreate, key: Key, db: Db, user: User):
    return mutation_response(await ReconciliationService.create(db, user, payload, key))


@reconciliation_controller.get('/reconciliations/{batch_id}', summary='读取对账批次及导入诊断')
async def get(request: Request, batch_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ReconciliationService.get(db, user, batch_id))


@reconciliation_controller.get('/reconciliations/{batch_id}/attachment/download', summary='授权下载原始账单证据')
@reconciliation_controller.head('/reconciliations/{batch_id}/attachment/download', summary='授权读取原始账单文件元数据')
async def attachment(request: Request, batch_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await ReconciliationService.download(
        db, user, batch_id, request.headers.get('range'), head=request.method == 'HEAD')
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@reconciliation_controller.get('/reconciliations', summary='筛选并分页读取对账批次')
async def listing(request: Request, query: Annotated[ReconciliationQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ReconciliationService.listing(db, user, query))


@reconciliation_controller.get('/reconciliations/{batch_id}/lines', summary='分页读取账单项及本次文件观察证据')
async def lines(request: Request, batch_id: ProjectId, query: Annotated[ReconciliationLineQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ReconciliationService.lines(db, user, batch_id, query))


@reconciliation_controller.post('/reconciliation-lines/{line_id}/match', summary='人工匹配同账号计费对象')
@Log(title='匹配账单项', business_type=BusinessType.UPDATE)
async def match(request: Request, line_id: ProjectId, payload: ReconciliationMatch, key: Key, db: Db, user: User):
    return mutation_response(await ReconciliationActionService.save(db, user, line_id, 'match', payload, key))


@reconciliation_controller.post('/reconciliation-lines/{line_id}/confirm', summary='确认已匹配账单项，不自动调整估值')
@Log(title='确认账单项', business_type=BusinessType.UPDATE)
async def confirm(request: Request, line_id: ProjectId, payload: ReconciliationConfirm, key: Key, db: Db, user: User):
    return mutation_response(await ReconciliationActionService.save(db, user, line_id, 'confirm', payload, key))


@reconciliation_controller.post('/reconciliation-lines/{line_id}/resolve', summary='选择导入证据解决差异，仍需人工确认')
@Log(title='处理账单差异', business_type=BusinessType.UPDATE)
async def resolve(request: Request, line_id: ProjectId, payload: ReconciliationResolve, key: Key, db: Db, user: User):
    return mutation_response(await ReconciliationActionService.save(db, user, line_id, 'resolve', payload, key))

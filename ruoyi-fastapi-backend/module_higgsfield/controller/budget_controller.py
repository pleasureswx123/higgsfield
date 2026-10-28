from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.budget_vo import BudgetCreate, BudgetUpdate, BudgetQuery
from module_higgsfield.service.budget_service import BudgetService
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.budget_period_vo import BudgetPeriodCreate, BudgetLimitUpdate, BudgetPeriodQuery
from module_higgsfield.service.budget_period_service import BudgetPeriodService


budget_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-预算'], order_num=92, dependencies=[PreAuthDependency()]
)


@budget_controller.get('/budgets', summary='按管理范围分页读取预算定义')
async def listing(request: Request, query: Annotated[BudgetQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await BudgetService.listing(db, user, query))


@budget_controller.post('/budgets', summary='创建明确口径的预算定义')
@Log(title='创建预算定义', business_type=BusinessType.INSERT)
async def create(request: Request, payload: BudgetCreate, key: Key, db: Db, user: User):
    return mutation_response(await BudgetService.save(db, user, payload, key))


@budget_controller.put('/budgets/{budget_id}', summary='启停预算，不释放已有预占')
@Log(title='启停预算', business_type=BusinessType.UPDATE)
async def update(request: Request, budget_id: ProjectId, payload: BudgetUpdate, key: Key, db: Db, user: User):
    return mutation_response(await BudgetService.save(db, user, payload, key, budget_id))


@budget_controller.get('/budgets/{budget_id}/periods', summary='分页读取预算周期余额')
async def periods(
    request: Request, budget_id: ProjectId, query: Annotated[BudgetPeriodQuery, Query()], db: Db, user: User
):
    return ResponseUtil.success(model_content=await BudgetPeriodService.listing(db, user, budget_id, query))


@budget_controller.post('/budgets/{budget_id}/periods', summary='初始化预算周期及额度账本')
@Log(title='初始化预算周期', business_type=BusinessType.INSERT)
async def create_period(
    request: Request, budget_id: ProjectId, payload: BudgetPeriodCreate, key: Key, db: Db, user: User
):
    return mutation_response(await BudgetPeriodService.save(db, user, budget_id, payload, key))


@budget_controller.post('/budget-periods/{period_id}/adjust-limit', summary='追加额度变动，不修改已用金额')
@Log(title='调整预算额度', business_type=BusinessType.UPDATE)
async def adjust_limit(
    request: Request, period_id: ProjectId, payload: BudgetLimitUpdate, key: Key, db: Db, user: User
):
    return mutation_response(await BudgetPeriodService.save(db, user, period_id, payload, key, adjust=True))


@budget_controller.get('/budget-periods/{period_id}/ledger', summary='分页读取预算不可变账本')
async def ledger(
    request: Request, period_id: ProjectId, query: Annotated[BudgetPeriodQuery, Query()], db: Db, user: User
):
    return ResponseUtil.success(
        model_content=await BudgetPeriodService.listing(db, user, period_id, query, ledger=True)
    )

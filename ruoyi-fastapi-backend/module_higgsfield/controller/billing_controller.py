"""后台费用调整入口，复用框架鉴权、日志和响应。"""

from typing import Annotated
from fastapi import Request, Query
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.billing_adjustment_vo import BillingAdjustmentInput
from module_higgsfield.service.billing_admin_service import BillingAdminService
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.billing_query_vo import BillingQuery
from module_higgsfield.entity.vo.usage_query_vo import UsageQuery
from module_higgsfield.service.usage_summary_service import UsageSummaryService


billing_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-费用'], order_num=93, dependencies=[PreAuthDependency()]
)


@billing_controller.get('/usage/summary', summary='按管理范围汇总项目费用与采用用量')
async def summary(request: Request, query: Annotated[UsageQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(data=await UsageSummaryService.summary(db, user, query))


@billing_controller.get('/billing-events', summary='按管理范围分页筛选项目费用')
async def listing(request: Request, query: Annotated[BillingQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await BillingAdminService.listing(db, user, query))


@billing_controller.get('/billing-events/{event_id}', summary='按费用管理范围读取计价明细与调整历史')
async def detail(request: Request, event_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await BillingAdminService.detail(db, user, event_id))


@billing_controller.post('/billing-events/{event_id}/adjustments', summary='追加费用调整并同步原预算账本')
@Log(title='调整费用', business_type=BusinessType.UPDATE)
async def adjust(request: Request, event_id: ProjectId, payload: BillingAdjustmentInput, key: Key, db: Db, user: User):
    return mutation_response(await BillingAdminService.adjust(db, user, event_id, payload, key))

"""制作端平台费用汇总，复用项目权限与框架响应。"""

from typing import Annotated
from fastapi import Request, Query
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId
from module_higgsfield.entity.vo.usage_query_vo import StudioUsageQuery
from module_higgsfield.service.usage_summary_service import UsageSummaryService
from utils.response_util import ResponseUtil
from module_higgsfield.service.budget_status_service import BudgetStatusService
from module_higgsfield.service.generation_policy_service import GenerationPolicyService


usage_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-用量'], order_num=94, dependencies=[PreAuthDependency()]
)


@usage_controller.get('/projects/{project_id}/budget-status', summary='读取当前预算阻断状态及获准平台额度')
async def budget_status(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(
        data=await BudgetStatusService.status(db, user, project_id, GenerationPolicyService.configured())
    )


@usage_controller.get('/me/usage/summary', summary='汇总本人且当前可访问项目的平台用量')
async def personal_summary(request: Request, query: Annotated[StudioUsageQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(data=await UsageSummaryService.personal_summary(db, user, query))


@usage_controller.get('/projects/{project_id}/usage/summary', summary='按项目费用权限汇总平台用量')
async def project_summary(
    request: Request, project_id: ProjectId, query: Annotated[StudioUsageQuery, Query()], db: Db, user: User
):
    return ResponseUtil.success(data=await UsageSummaryService.project_summary(db, user, project_id, query))

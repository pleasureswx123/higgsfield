"""制作端仅保留预算阻断提示；费用汇总统一由后台管理。"""

from fastapi import Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId
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

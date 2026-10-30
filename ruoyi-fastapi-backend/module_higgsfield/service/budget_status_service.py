"""制作端提交前预算状态；最终受理仍按实际估价重新校验并原子预占。"""

from decimal import localcontext
from module_higgsfield.dao.budget_status_dao import BudgetStatusDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.budget_period_service import BudgetPeriodService


class BudgetStatusService:
    @staticmethod
    async def status(db, user, project_id, policy):
        project, role, allowed = await WorkspaceService.authorize(
            db, user, project_id, 'project:read', owner_id=user.user.user_id
        )
        rows = await BudgetStatusDao.current(db, project_id, user.user.user_id)
        codes, periods, seen = set(), [], set()
        visible = False  # 制作端仅返回阻断状态，不返回预算金额。
        scopes = await WorkspaceDao.permission_scopes(db, role, project_id)
        if project.status != '0':
            codes.add('PROJECT_READ_ONLY')
        if 'generation:create' not in allowed:
            codes.add('GENERATION_PERMISSION_REQUIRED')
        if not rows and policy.missing_budget_policy == 'reject':
            codes.add('BUDGET_REQUIRED')
        with localcontext() as context:
            context.prec = 100
            for budget, period in rows:
                if budget.budget_id in seen:
                    codes.add('BUDGET_PERIOD_AMBIGUOUS')
                seen.add(budget.budget_id)
                if period is None:
                    codes.add('BUDGET_PERIOD_REQUIRED')
                    continue
                if period.limit_amount - period.reserved_amount - period.consumed_amount <= 0:
                    codes.add('BUDGET_INSUFFICIENT')
                if budget.currency != policy.currencies()[budget.purpose]:
                    codes.add('BUDGET_ESTIMATE_REQUIRED')
                # 制作端费用读取权仅覆盖平台口径，采购预算只影响可提交状态。
                if (
                    visible
                    and budget.purpose == 'platform'
                    and (scopes.get('project:usage:read') == 'project' or budget.user_id == user.user.user_id)
                ):
                    periods.append(
                        BudgetPeriodService.result(period) | {'purpose': 'platform', 'currency': budget.currency}
                    )
        result = {
            'canSubmit': not codes,
            'blockingCodes': sorted(codes),
            'amountVisibility': 'visible' if visible else 'hidden',
        }
        if visible:
            result['periods'] = periods
        return result

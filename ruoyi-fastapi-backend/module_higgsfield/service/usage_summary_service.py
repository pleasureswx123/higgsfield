"""管理用量汇总，授权在事实查询前执行。"""

from exceptions.exception import PermissionException
from module_higgsfield.dao.usage_summary_dao import UsageSummaryDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.usage_summary_calculation_service import UsageSummaryFact, UsageSummaryCalculationService


class UsageSummaryService:
    @staticmethod
    async def personal_summary(db, user, query):
        if query.scope != 'project' or query.purpose != 'platform' or query.user_id is not None:
            raise PermissionException(message='本人汇总只支持平台口径，不能指定用户')
        if 'project:usage:read' not in user.permissions and '*:*:*' not in user.permissions:
            raise PermissionException(message='没有平台费用读取权限')
        if not await UsageSummaryDao.has_personal_access(db, user.user.user_id):
            raise PermissionException(message='没有可读取费用的项目范围')
        if query.project_id is not None:
            await WorkspaceService.authorize(
                db, user, int(query.project_id), 'project:usage:read', owner_id=user.user.user_id
            )
        facts = await UsageSummaryDao.facts(db, None, None, query, personal_actor=user.user.user_id)
        return {
            'timeBasis': query.time_basis,
            'businessTimezone': query.business_timezone,
            'purpose': 'platform',
            'rows': UsageSummaryCalculationService.summarize(
                (UsageSummaryFact(**row) for row in facts), purpose='platform'
            ),
        }

    @staticmethod
    async def project_summary(db, user, project_id, query):
        if query.scope != 'project' or query.purpose != 'platform' or query.user_id is not None:
            raise PermissionException(message='制作端只可读取平台费用，不可指定用户')
        if query.project_id is not None and int(query.project_id) != project_id:
            WorkspaceService.conflict('USAGE_PROJECT_MISMATCH', '查询项目与路由项目不一致')
        _, role, _ = await WorkspaceService.authorize(
            db, user, project_id, 'project:usage:read', owner_id=user.user.user_id
        )
        scopes = await WorkspaceDao.permission_scopes(db, role)
        own_actor = user.user.user_id if scopes.get('project:usage:read') == 'own' else None
        facts = await UsageSummaryDao.facts(db, None, None, query, authorized_project=project_id, own_actor=own_actor)
        return {
            'timeBasis': query.time_basis,
            'businessTimezone': query.business_timezone,
            'purpose': 'platform',
            'rows': UsageSummaryCalculationService.summarize(
                (UsageSummaryFact(**row) for row in facts), purpose='platform'
            ),
        }

    @staticmethod
    async def summary(db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'billing:read')
        if query.scope == 'cost_center' and not any(role['data_scope'] == '1' for role in roles):
            raise PermissionException(message='成本中心汇总要求全部管理范围')
        if query.purpose == 'procurement' and not any(role['data_scope'] == '1' for role in roles):
            raise PermissionException(message='采购汇总当前要求全部管理范围')
        facts = await UsageSummaryDao.facts(db, actor, roles, query)
        rows = UsageSummaryCalculationService.summarize(
            (UsageSummaryFact(**row) for row in facts), purpose=query.purpose
        )
        return {
            'timeBasis': query.time_basis,
            'businessTimezone': query.business_timezone,
            'purpose': query.purpose,
            'scope': query.scope,
            'rows': rows,
        }

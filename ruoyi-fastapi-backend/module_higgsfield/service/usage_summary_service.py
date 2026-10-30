"""管理用量汇总，授权在事实查询前执行。"""

from exceptions.exception import PermissionException
from module_higgsfield.dao.usage_summary_dao import UsageSummaryDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.usage_summary_calculation_service import UsageSummaryFact, UsageSummaryCalculationService


class UsageSummaryService:
    @staticmethod
    async def personal_summary(db, user, query):
        raise PermissionException(message='制作端不提供费用汇总，请由费用管理员在后台查询')

    @staticmethod
    async def project_summary(db, user, project_id, query):
        raise PermissionException(message='制作端不提供费用汇总，请由费用管理员在后台查询')

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

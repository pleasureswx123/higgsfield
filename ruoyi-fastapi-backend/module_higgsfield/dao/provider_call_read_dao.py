"""调用范围沿任务项目创建人过滤，非项目调用仅全部范围可见。"""
from sqlalchemy import text
from module_higgsfield.dao.budget_dao import BudgetDao

STATES = {'planned': '0', 'sending': '1', 'completed': '2', 'unknown': '3'}


class ProviderCallReadDao:
    @staticmethod
    def scoped(actor, roles):
        scope, params = BudgetDao.scope(actor, roles)
        return (' FROM hf_provider_call c LEFT JOIN hf_creation_job j ON j.job_id=c.job_id'
                ' LEFT JOIN hf_project p ON p.project_id=j.project_id'
                ' LEFT JOIN sys_user u ON u.user_id=p.create_user_id WHERE ' + scope), params

    @classmethod
    async def page(cls, db, query, actor, roles):
        sql, params = cls.scoped(actor, roles)
        for key in ('job_id', 'account_id'):
            if getattr(query, key) is not None:
                sql += f' AND c.{key}=:{key}'
                params[key] = int(getattr(query, key))
        if query.state:
            sql += ' AND c.state=:state'
            params['state'] = STATES[query.state]
        for key, operator in (('from_time', '>='), ('to_time', '<')):
            if getattr(query, key) is not None:
                sql += f' AND c.create_time{operator}:{key}'
                params[key] = getattr(query, key)
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text(
            'SELECT c.call_id,c.job_id,c.cost_center_id,c.operation,c.state,c.acceptance,'
            'c.http_status,c.business_code,c.started_time,c.finished_time' + sql +
            ' ORDER BY c.create_time DESC,c.call_id DESC LIMIT :limit OFFSET :offset'
        ), params)).all()
        return rows, total

    @classmethod
    async def detail(cls, db, identity, actor, roles):
        sql, params = cls.scoped(actor, roles)
        params['identity'] = identity
        return (await db.execute(text('SELECT c.*' + sql + ' AND c.call_id=:identity'), params)).first()

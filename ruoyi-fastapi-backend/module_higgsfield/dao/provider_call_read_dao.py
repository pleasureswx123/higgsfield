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
                ' LEFT JOIN sys_user u ON u.user_id=p.create_user_id'
                ' LEFT JOIN sys_user caller ON caller.user_id=COALESCE(j.actor_id,c.actor_id) WHERE ' + scope), params

    @staticmethod
    def caller_columns():
        return (",NULLIF(COALESCE(j.actor_id,c.actor_id),1) AS caller_id,"
                "CASE WHEN COALESCE(j.actor_id,c.actor_id)=1 THEN NULL ELSE caller.user_name END AS caller_username,"
                "CASE WHEN COALESCE(j.actor_id,c.actor_id)=1 THEN '系统账号' ELSE caller.nick_name END AS caller_name")

    @staticmethod
    def asset_columns():
        # 只读取素材查询证据；名称须属于任务固定引用，避免越过管理范围。
        return (",CASE WHEN c.operation IN ('asset_get','upload','register') THEN c.request_metadata ELSE NULL END AS asset_evidence,CASE WHEN c.operation='upload' THEN c.response_metadata ELSE NULL END AS upload_result,"
                "(SELECT a.asset_name FROM hf_asset_version v JOIN hf_asset a ON a.asset_id=v.asset_id "
                "WHERE c.operation IN ('asset_get','upload','register') AND v.version_id::text=c.request_metadata->>'assetVersionId' "
                "AND EXISTS(SELECT 1 FROM hf_job_reference r WHERE r.job_id=j.job_id AND r.asset_version_id=v.version_id) "
                "LIMIT 1) AS asset_name")

    @classmethod
    def filtered(cls, query, actor, roles):
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
        return sql, params

    @classmethod
    async def page(cls, db, query, actor, roles):
        sql, params = cls.filtered(query, actor, roles)
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text(
            'SELECT c.call_id,c.job_id,c.cost_center_id,c.operation,c.state,c.acceptance,'
            'c.http_status,c.business_code,c.started_time,c.finished_time' + cls.caller_columns() + cls.asset_columns() + sql +
            ' ORDER BY c.create_time DESC,c.call_id DESC LIMIT :limit OFFSET :offset'
        ), params)).all()
        return rows, total

    @classmethod
    async def tasks(cls, db, query, actor, roles):
        sql, params = cls.filtered(query, actor, roles)
        # 筛选决定哪些任务入选，次数始终统计该任务完整调用，不能只统计命中的分页。
        matched = 'SELECT DISTINCT c.job_id' + sql + ' AND c.job_id IS NOT NULL'
        total = await db.scalar(text('SELECT count(*) FROM (' + matched + ') matched'), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text(
            'WITH matched AS (' + matched + ') SELECT j.job_id,j.project_id,j.kind,'
            'j.orchestration_state,j.upstream_state,j.create_time,j.finished_time,'
            "NULLIF(j.actor_id,1) AS caller_id,CASE WHEN j.actor_id=1 THEN NULL ELSE caller.user_name END AS caller_username,"
            "CASE WHEN j.actor_id=1 THEN '系统账号' ELSE caller.nick_name END AS caller_name,"
            '(SELECT count(*) FROM hf_provider_call c WHERE c.job_id=j.job_id) AS call_count,'
            "(SELECT count(*) FROM hf_provider_call c WHERE c.job_id=j.job_id AND c.operation='video_poll') AS poll_count "
            'FROM matched JOIN hf_creation_job j ON j.job_id=matched.job_id '
            'LEFT JOIN sys_user caller ON caller.user_id=j.actor_id '
            'ORDER BY j.create_time DESC,j.job_id DESC LIMIT :limit OFFSET :offset'
        ), params)).all()
        return rows, total

    @classmethod
    async def process(cls, db, identity, actor, roles):
        sql, params = cls.scoped(actor, roles)
        params['identity'] = identity
        return (await db.execute(text('SELECT c.call_id,c.job_id,c.cost_center_id,c.operation,c.state,c.acceptance,'
            'c.http_status,c.business_code,c.started_time,c.finished_time' + cls.caller_columns() + cls.asset_columns() + sql +
            ' AND c.job_id=:identity ORDER BY c.create_time,c.call_id'), params)).all()

    @classmethod
    async def detail(cls, db, identity, actor, roles):
        sql, params = cls.scoped(actor, roles)
        params['identity'] = identity
        return (await db.execute(text('SELECT c.*' + cls.caller_columns() + cls.asset_columns() + sql + ' AND c.call_id=:identity'), params)).first()

    @staticmethod
    async def task(db, job_id):
        return (await db.execute(text(
            'SELECT job_id,project_id,actor_id,kind,model_version_id,input_snapshot,'
            'orchestration_state,upstream_state,create_time,finished_time FROM hf_creation_job WHERE job_id=:id'
        ), {'id': job_id})).first()

    @staticmethod
    async def task_assets(db, job_id):
        return (await db.execute(text(
            'SELECT r.asset_version_id,a.asset_name FROM hf_job_reference r '
            'JOIN hf_asset_version v ON v.version_id=r.asset_version_id '
            'JOIN hf_asset a ON a.asset_id=v.asset_id WHERE r.job_id=:id'
        ), {'id': job_id})).all()

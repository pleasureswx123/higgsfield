"""异常条件与管理范围均在数据库分页之前生效。"""
from sqlalchemy import text
from module_higgsfield.dao.budget_dao import BudgetDao


class IncidentReadDao:
    @staticmethod
    async def retryable_archive(db, identity):
        return bool(await db.scalar(text("""SELECT count(*)>0 AND bool_and(
            kind IN ('image','video') AND source_url_ciphertext IS NOT NULL
            AND (source_expires_time IS NULL OR source_expires_time>clock_timestamp()))
            FROM hf_generated_output WHERE job_id=:id AND del_flag='0' AND archive_state='3'"""), {'id': identity}))

    CONDITIONS = {
        'submission_unknown': "j.orchestration_state='3'",
        'blocked': "j.orchestration_state='6'",
        'upstream_unknown': "j.upstream_state='6'",
        'upstream_failed': "j.upstream_state='4'",
        'archive_failed': "EXISTS(SELECT 1 FROM hf_generated_output o WHERE o.job_id=j.job_id AND o.del_flag='0' AND o.archive_state='3')",
        'source_expired': "EXISTS(SELECT 1 FROM hf_generated_output o WHERE o.job_id=j.job_id AND o.del_flag='0' AND o.archive_state='4')",
        'billing_disputed': "j.billing_state='3'",
    }
    COLUMNS = ('j.job_id,j.project_id,j.actor_id,j.revision,j.orchestration_state,j.upstream_state,'
               'j.billing_state,j.next_action_time,j.create_time,j.update_time,j.kind,j.lease_until,j.upstream_task_id,j.credential_version_id')

    @classmethod
    def scoped(cls, actor, roles):
        scope, params = BudgetDao.scope(actor, roles)
        return (' FROM hf_creation_job j JOIN hf_project p ON p.project_id=j.project_id'
                ' LEFT JOIN sys_user u ON u.user_id=p.create_user_id WHERE ' + scope), params

    @classmethod
    async def page(cls, db, query, actor, roles):
        sql, params = cls.scoped(actor, roles)
        sql += ' AND (' + (cls.CONDITIONS[query.state] if query.state else ' OR '.join(cls.CONDITIONS.values())) + ')'
        if query.project_id:
            sql += ' AND j.project_id=:project_id'
            params['project_id'] = int(query.project_id)
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text('SELECT ' + cls.COLUMNS + sql +
            ' ORDER BY j.update_time DESC,j.job_id DESC LIMIT :limit OFFSET :offset'), params)).all()
        return rows, total

    @classmethod
    async def detail(cls, db, identity, actor, roles):
        sql, params = cls.scoped(actor, roles)
        params['identity'] = identity
        # 允许复查已经恢复的任务，详情不因退出异常队列而消失。
        return (await db.execute(text('SELECT ' + cls.COLUMNS + sql + ' AND j.job_id=:identity'), params)).first()

    @staticmethod
    async def evidence(db, identities):
        if not identities:
            return {}, {}
        summaries = {identity: dict(total=0, ready=0, failed=0, pending=0) for identity in identities}
        rows = (await db.execute(text("SELECT job_id,archive_state,count(*) AS amount FROM hf_generated_output WHERE job_id=ANY(CAST(:ids AS bigint[])) AND del_flag='0' GROUP BY job_id,archive_state"), {'ids': identities})).all()
        for row in rows:
            summary = summaries[row.job_id]
            summary['total'] += row.amount
            key = 'ready' if row.archive_state in {'2', '5'} else 'failed' if row.archive_state in {'3', '4'} else 'pending'
            summary[key] += row.amount
        calls = (await db.execute(text('SELECT DISTINCT ON (job_id) job_id,call_id,acceptance,state FROM hf_provider_call WHERE job_id=ANY(CAST(:ids AS bigint[])) ORDER BY job_id,create_time DESC,call_id DESC'), {'ids': identities})).all()
        return summaries, {row.job_id: row for row in calls}

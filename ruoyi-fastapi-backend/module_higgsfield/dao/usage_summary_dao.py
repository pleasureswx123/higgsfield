"""汇总只取授权范围内的单事件事实，不连接多行明细造成金额放大。"""

from sqlalchemy import text
from module_higgsfield.dao.budget_dao import BudgetDao


class UsageSummaryDao:
    member_scope = """EXISTS(SELECT 1 FROM hf_project_member pm
        JOIN hf_project_role role ON role.role_id=pm.role_id
        LEFT JOIN hf_project_role_permission rp ON rp.role_id=pm.role_id AND rp.permission_code='project:usage:read'
        LEFT JOIN hf_project_permission_config cfg ON cfg.project_id=pm.project_id
        JOIN sys_user me ON me.user_id=pm.user_id
        WHERE pm.project_id=p.project_id AND pm.user_id=:me AND pm.status='0'
        AND me.status='0' AND me.del_flag='0'
        AND (role.code='owner' OR COALESCE(cfg.overrides->role.code->>'project:usage:read',rp.data_scope) IN ('project','own')))"""

    @classmethod
    async def has_personal_access(cls, db, user_id):
        return await db.scalar(
            text("SELECT EXISTS(SELECT 1 FROM hf_project p WHERE p.del_flag='0' AND " + cls.member_scope + ')'),
            {'me': user_id},
        )

    @staticmethod
    async def facts(db, actor, roles, query, *, authorized_project=None, own_actor=None, personal_actor=None):
        if query.scope == 'cost_center':
            if authorized_project is not None or own_actor is not None or personal_actor is not None:
                raise ValueError('制作端范围不能读取成本中心汇总')
            return await UsageSummaryDao.cost_center_facts(db, roles, query)
        if personal_actor is not None:
            scope, params = 'j.actor_id=:me AND ' + UsageSummaryDao.member_scope, {'me': personal_actor}
        elif authorized_project is None:
            scope, params = BudgetDao.scope(actor, roles)
        else:
            scope, params = 'j.project_id=:authorized_project', {'authorized_project': authorized_project}
            if own_actor is not None:
                scope += ' AND j.actor_id=:own_actor'
                params['own_actor'] = own_actor
        params.update(purpose=query.purpose, start=query.from_time, end=query.to_time, timezone=query.business_timezone)
        day = "to_char(timezone(:timezone,e.create_time),'YYYY-MM-DD')"
        groups = {
            'project': ('CAST(p.project_id AS text)', 'p.project_name'),
            'user': ('CAST(j.actor_id AS text)', "coalesce(v.nick_name,v.user_name,'已删除用户')"),
            'department': (
                "coalesce(j.department_snapshot->>'deptId','unknown')",
                "coalesce(j.department_snapshot->>'deptName','未知部门')",
            ),
            'model': ("coalesce(CAST(m.model_id AS text),'unknown')", "coalesce(m.display_name,'未知模型')"),
            'day': (day, day),
        }
        key, name = groups[query.group_by]
        sql = f"""SELECT e.event_id,e.subject_id,{key} AS group_key,{name} AS display_name,
            e.purpose,e.currency,e.state,e.amount,
            (SELECT coalesce(sum(a.delta_amount),0) FROM hf_billing_adjustment a WHERE a.event_id=e.event_id) AS adjustment_total,
            r.input_tokens,r.output_tokens,r.video_tokens,coalesce(r.completeness,'unknown') AS usage_completeness
            FROM hf_billing_event e JOIN hf_billing_subject s ON s.subject_id=e.subject_id
            JOIN hf_creation_job j ON j.job_id=s.job_id JOIN hf_project p ON p.project_id=j.project_id
            JOIN sys_user u ON u.user_id=p.create_user_id LEFT JOIN sys_user v ON v.user_id=j.actor_id
            LEFT JOIN hf_model_profile_version mv ON mv.model_version_id=j.model_version_id
            LEFT JOIN hf_model_profile m ON m.model_id=mv.model_id
            LEFT JOIN hf_usage_record r ON r.usage_id=e.usage_record_id AND r.subject_id=s.subject_id
            WHERE p.del_flag='0' AND u.del_flag='0' AND e.purpose=:purpose
            AND e.create_time>=:start AND e.create_time<:end AND {scope}"""
        for field, column in (
            ('project_id', 'j.project_id'),
            ('user_id', 'j.actor_id'),
            ('model_id', 'm.model_id'),
            ('currency', 'e.currency'),
            ('department_id', "j.department_snapshot->>'deptId'"),
        ):
            value = getattr(query, field)
            if value is not None:
                sql += f' AND {column}=:{field}'
                params[field] = int(value) if field in {'project_id', 'user_id', 'model_id'} else value
        return (await db.execute(text(sql + ' ORDER BY e.event_id'), params)).mappings().all()

    @staticmethod
    async def cost_center_facts(db, roles, query):
        # 无项目的管理消费只能由对应权限的全部范围角色读取。
        if not roles or not any(role['data_scope'] == '1' for role in roles):
            return []
        day = "to_char(timezone(:timezone,e.create_time),'YYYY-MM-DD')"
        key, name = {
            'cost_center': ('CAST(s.cost_center_id AS text)', "coalesce(c.cost_center_name,'未知成本中心')"),
            'day': (day, day),
        }[query.group_by]
        sql = f"""SELECT e.event_id,e.subject_id,{key} AS group_key,{name} AS display_name,
            e.purpose,e.currency,e.state,e.amount,
            (SELECT coalesce(sum(a.delta_amount),0) FROM hf_billing_adjustment a WHERE a.event_id=e.event_id) AS adjustment_total,
            r.input_tokens,r.output_tokens,r.video_tokens,coalesce(r.completeness,'unknown') AS usage_completeness
            FROM hf_billing_event e JOIN hf_billing_subject s ON s.subject_id=e.subject_id
            LEFT JOIN hf_cost_center c ON c.cost_center_id=s.cost_center_id
            LEFT JOIN hf_usage_record r ON r.usage_id=e.usage_record_id AND r.subject_id=s.subject_id
            WHERE s.job_id IS NULL AND s.cost_center_id IS NOT NULL AND e.purpose=:purpose
            AND e.create_time>=:start AND e.create_time<:end"""
        params = dict(purpose=query.purpose, start=query.from_time, end=query.to_time, timezone=query.business_timezone)
        for field, column in (('cost_center_id', 's.cost_center_id'), ('currency', 'e.currency')):
            value = getattr(query, field)
            if value is not None:
                sql += f' AND {column}=:{field}'
                params[field] = int(value) if field == 'cost_center_id' else value
        return (await db.execute(text(sql + ' ORDER BY e.event_id'), params)).mappings().all()

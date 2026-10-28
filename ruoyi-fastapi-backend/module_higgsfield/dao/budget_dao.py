"""预算主体串行锁和分页前管理范围过滤，不从无关角色扩大范围。"""

from hashlib import sha256
from sqlalchemy import select, func, text
from module_higgsfield.entity.do.budget_do import HfBudget


class BudgetDao:
    @staticmethod
    def scope(actor, roles):
        params = {'actor_id': actor['user_id'], 'actor_dept': actor['dept_id']}
        scopes = {role['data_scope'] for role in roles}
        if '1' in scopes:
            return 'TRUE', params
        clauses = []
        if '5' in scopes:
            clauses.append('u.user_id=:actor_id')
        if '2' in scopes:
            params['role_ids'] = [role['role_id'] for role in roles if role['data_scope'] == '2']
            clauses.append(
                "EXISTS(SELECT 1 FROM sys_role_dept rd JOIN sys_dept d ON d.dept_id=rd.dept_id WHERE rd.role_id=ANY(CAST(:role_ids AS bigint[])) AND rd.dept_id=u.dept_id AND d.status='0' AND d.del_flag='0')"
            )
        if scopes & {'3', '4'} and actor['dept_id'] is not None:
            descendants = " OR CAST(s.dept_id AS text)=ANY(string_to_array(d.ancestors,','))" if '4' in scopes else ''
            clauses.append(
                "EXISTS(SELECT 1 FROM sys_dept s JOIN sys_dept d ON d.dept_id=u.dept_id WHERE s.dept_id=:actor_dept AND s.status='0' AND s.del_flag='0' AND d.status='0' AND d.del_flag='0' AND (d.dept_id=s.dept_id"
                + descendants
                + '))'
            )
        return '(' + ' OR '.join(clauses) + ')' if clauses else 'FALSE', params

    @staticmethod
    async def lock_subject(db, kind, identity):
        key = int.from_bytes(sha256(f'hf:budget:{kind}:{identity}'.encode()).digest()[:8], signed=True)
        await db.execute(select(func.pg_advisory_xact_lock(key)))

    @classmethod
    async def subject(cls, db, kind, identity, actor, roles):
        scope, params = cls.scope(actor, roles)
        params['identity'] = int(identity)
        if kind == 'project':
            sql = "SELECT p.project_id AS id,p.status FROM hf_project p JOIN sys_user u ON u.user_id=p.create_user_id WHERE p.project_id=:identity AND p.del_flag='0' AND u.del_flag='0' AND "
        else:
            sql = "SELECT u.user_id AS id,u.status FROM sys_user u WHERE u.user_id=:identity AND u.del_flag='0' AND "
        return (await db.execute(text(sql + scope), params)).first()

    @staticmethod
    async def get(db, identity, lock=False):
        statement = select(HfBudget).where(HfBudget.budget_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def existing(db, payload):
        subject = payload.subject
        return await db.scalar(
            select(HfBudget.budget_id).where(
                HfBudget.project_id == (int(subject.project_id) if subject.project_id else None),
                HfBudget.user_id == (int(subject.user_id) if subject.user_id else None),
                HfBudget.purpose == payload.purpose,
                HfBudget.currency == payload.currency,
                HfBudget.cycle_kind == payload.cycle_kind,
            )
        )

    @staticmethod
    async def add(db, values):
        row = HfBudget(**values)
        db.add(row)
        await db.flush()
        return row

    @classmethod
    async def page(cls, db, query, actor, roles):
        scope, params = cls.scope(actor, roles)
        sql = (
            " FROM hf_budget b LEFT JOIN hf_project p ON p.project_id=b.project_id JOIN sys_user u ON u.user_id=COALESCE(b.user_id,p.create_user_id) WHERE u.del_flag='0' AND (b.project_id IS NULL OR p.del_flag='0') AND "
            + scope
        )
        if query.subject_type:
            column = 'b.project_id' if query.subject_type == 'project' else 'b.user_id'
            sql += ' AND ' + column + ' IS NOT NULL'
            if query.subject_id:
                sql += ' AND ' + column + '=:subject_id'
                params['subject_id'] = int(query.subject_id)
        if not any(role['data_scope'] == '1' for role in roles):
            sql += " AND b.purpose='platform'"
        if query.purpose:
            sql += ' AND b.purpose=:purpose'
            params['purpose'] = query.purpose
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(offset=(query.page_num - 1) * query.page_size, limit=query.page_size)
        rows = (
            await db.execute(
                text('SELECT b.*' + sql + ' ORDER BY b.budget_id DESC OFFSET :offset LIMIT :limit'), params
            )
        ).all()
        return rows, total

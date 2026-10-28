"""在统计和分页前限制审计范围；历史记录不随项目逻辑删除消失。"""
from sqlalchemy import text
from module_higgsfield.dao.budget_dao import BudgetDao


class AuditReadDao:
    @staticmethod
    async def page(db, query, actor, roles):
        scope, params = BudgetDao.scope(actor, roles)
        # 无项目归属的全局配置证据仅向全部管理范围开放。
        sql = (' FROM hf_audit_log a LEFT JOIN hf_project p ON p.project_id=a.project_id'
               ' LEFT JOIN sys_user u ON u.user_id=p.create_user_id WHERE ' + scope)
        for column, value in (
            ('object_type', query.object_type), ('object_id', query.object_id),
            ('actor_id', int(query.actor_id) if query.actor_id is not None else None),
        ):
            if value is not None:
                sql += f' AND a.{column}=:{column}'
                params[column] = value
        if query.from_time is not None:
            sql += ' AND a.create_time>=:from_time'
            params['from_time'] = query.from_time
        if query.to_time is not None:
            sql += ' AND a.create_time<:to_time'
            params['to_time'] = query.to_time
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text(
            'SELECT a.audit_id,a.actor_id,a.actor_kind,a.object_type,a.object_id,a.action,'
            'a.reason,a.create_time,a.before_after' + sql +
            ' ORDER BY a.create_time DESC,a.audit_id DESC LIMIT :limit OFFSET :offset'
        ), params)).all()
        return rows, total

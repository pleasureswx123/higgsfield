"""治理写入锁定项目行，返回元数据而非制作内容。"""
from sqlalchemy import select, text
from module_higgsfield.entity.do.project_do import HfProject
from module_higgsfield.dao.budget_dao import BudgetDao
from module_higgsfield.dao.project_dao import STATUS_CODES


class ProjectGovernanceDao:
    @staticmethod
    async def page(db, query, actor, roles):
        # 复用既有创建人/部门管理范围谓词，u为项目创建人，不要求制作成员身份。
        scope, params = BudgetDao.scope(actor, roles)
        sql = " FROM hf_project p LEFT JOIN sys_user u ON u.user_id=p.create_user_id WHERE p.del_flag='0' AND " + scope
        if query.q.strip():
            sql += " AND p.project_name ILIKE :query ESCAPE '\\'"
            params['query'] = '%' + query.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        if query.status:
            sql += ' AND p.status=:status'
            params['status'] = STATUS_CODES[query.status]
        total = await db.scalar(text('SELECT count(*)' + sql), params)
        params.update(limit=query.page_size, offset=(query.page_num - 1) * query.page_size)
        rows = (await db.execute(text('SELECT p.project_id,p.project_name,p.status,p.revision,p.create_time,p.update_time'
                                     + sql + ' ORDER BY p.create_time DESC,p.project_id DESC LIMIT :limit OFFSET :offset'), params)).all()
        return rows, total

    @staticmethod
    async def locked(db, identity):
        return await db.scalar(select(HfProject).where(HfProject.project_id == identity)
                               .with_for_update().execution_options(populate_existing=True))

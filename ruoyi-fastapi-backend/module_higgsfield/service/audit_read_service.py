"""只返回持久化的非秘密审计事实，不查询制作正文或供应商原始请求。"""
from common.vo import PageModel
from module_higgsfield.dao.audit_read_dao import AuditReadDao
from module_higgsfield.service.admin_scope_service import AdminScopeService


class AuditReadService:
    @staticmethod
    async def listing(db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'audit:read')
        rows, total = await AuditReadDao.page(db, query, actor, roles)
        return PageModel(rows=[{
            'id': str(row.audit_id), 'actorId': str(row.actor_id) if row.actor_id is not None else None,
            'actorKind': row.actor_kind, 'objectType': row.object_type, 'objectId': row.object_id,
            'action': row.action, 'reason': row.reason, 'createTime': row.create_time.isoformat(),
            'diff': row.before_after,
        } for row in rows], total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total)

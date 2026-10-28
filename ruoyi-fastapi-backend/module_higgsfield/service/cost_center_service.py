"""非项目成本中心要求相应功能具有全部管理范围。"""
from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.cost_center_dao import CostCenterDao
from module_higgsfield.service.admin_scope_service import AdminScopeService


class CostCenterService:
    @staticmethod
    async def listing(db, user, query):
        authorized = False
        for permission in ('credential:test', 'billing:read'):
            if permission not in user.permissions and '*:*:*' not in user.permissions:
                continue
            try:
                await AdminScopeService.global_access(db, user, permission)
            except PermissionException:
                continue
            authorized = True
            break
        if not authorized:
            raise PermissionException(message='读取管理成本中心需要凭据测试或费用读取权限及全部管理范围')
        rows, total = await CostCenterDao.page(db, query)
        return PageModel(rows=[{'id': str(row.cost_center_id), 'code': row.code,
            'name': row.cost_center_name, 'active': row.active == 'Y'} for row in rows], total=total,
            pageNum=query.page_num, pageSize=query.page_size, hasNext=query.page_num * query.page_size < total)

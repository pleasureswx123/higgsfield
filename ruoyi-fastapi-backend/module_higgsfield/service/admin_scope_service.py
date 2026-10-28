"""管理元数据范围独立于制作端成员权限，不授予项目内容访问权。"""

from exceptions.exception import PermissionException
from module_higgsfield.dao.admin_scope_dao import AdminScopeDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class AdminScopeService:
    @staticmethod
    async def context(db, user, permission):
        if permission not in user.permissions and '*:*:*' not in user.permissions:
            raise PermissionException(message='没有此管理功能权限')
        actor = await AdminScopeDao.actor(db, user.user.user_id)
        if actor is None:
            raise PermissionException(message='当前用户已停用或删除')
        # admin 是现有鉴权链提供的系统管理员属性，不从通配权限字符串推断。
        if getattr(user.user, 'admin', False):
            return actor, [{'role_id': None, 'data_scope': '1'}]
        roles = await AdminScopeDao.scopes(db, actor['user_id'], permission)
        if not roles:
            raise PermissionException(message='此管理功能的角色授权已失效')
        return actor, roles

    @classmethod
    async def global_access(cls, db, user, permission):
        _, roles = await cls.context(db, user, permission)
        if not any(role['data_scope'] == '1' for role in roles):
            raise PermissionException(message='此功能要求提供相应权限的角色具有全部管理范围')

    @classmethod
    async def project(cls, db, user, project_id, permission, write=False):
        actor, roles = await cls.context(db, user, permission)
        project = await AdminScopeDao.project(db, project_id, lock=write)
        if project is None or project['del_flag'] != '0':
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '项目不存在或不在管理范围内')
        allowed = any(
            role['data_scope'] == '1' or (role['data_scope'] == '5' and project['create_user_id'] == actor['user_id'])
            for role in roles
        )
        dept = project['dept_id']
        if not allowed and dept is not None:
            custom = [role['role_id'] for role in roles if role['data_scope'] == '2']
            if custom:
                allowed = await AdminScopeDao.custom_department(db, custom, dept)
            if not allowed and actor['dept_id'] is not None and any(role['data_scope'] in ('3', '4') for role in roles):
                allowed = await AdminScopeDao.department_contains(
                    db, actor['dept_id'], dept, any(role['data_scope'] == '4' for role in roles)
                )
        if not allowed:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '项目不存在或不在管理范围内')
        if write and project['status'] != '0':
            WorkspaceService.conflict('PROJECT_READ_ONLY', '暂停、归档或待删除项目不能修改模型路由')
        return project

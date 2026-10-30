"""发送意图事务内读取并锁定原执行用户的当前项目授权。"""
from sqlalchemy import text
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao


class GenerationActorDao:
    @staticmethod
    async def system_access(db, actor_id, permission_code='generation:create'):
        """沿用若依有效角色与菜单权限规则，角色1是框架明确的管理员角色。"""
        roles = list(await db.scalars(text('''
            SELECT r.role_id FROM sys_user_role ur JOIN sys_role r ON r.role_id=ur.role_id
            WHERE ur.user_id=:actor AND r.status='0' AND r.del_flag='0'
            ORDER BY r.role_id FOR SHARE OF ur,r
        '''), {'actor': actor_id}))
        if 1 in roles:
            return True
        if not roles:
            return False
        permission = await db.scalar(text('''
            SELECT m.menu_id FROM sys_role_menu rm JOIN sys_menu m ON m.menu_id=rm.menu_id
            WHERE rm.role_id=ANY(CAST(:roles AS bigint[])) AND m.status='0'
                AND m.perms IN (:permission,'*:*:*')
            ORDER BY m.menu_id FOR SHARE OF rm,m
        '''), {'roles': roles, 'permission': permission_code})
        return permission is not None

    @staticmethod
    async def project_access(db, project_id, actor_id):
        actor = await WorkspaceDao.user(db, actor_id, lock=True)
        if actor is None or actor['status'] != '0' or actor['del_flag'] != '0':
            return False
        # 项目行由调用方先锁定；共享锁使成员撤回和角色授权删除与意图提交有确定顺序。
        role = await db.scalar(text("""
            SELECT r.code FROM hf_project_member m
            JOIN hf_project_role r ON r.role_id=m.role_id
            WHERE m.project_id=:project AND m.user_id=:actor AND m.status='0'
            FOR SHARE OF m,r
        """), {'project': project_id, 'actor': actor_id})
        if role is None:
            return False
        scopes = await WorkspaceDao.permission_scopes(db, role, project_id)
        return scopes.get('project:read') == 'project' and scopes.get('generation:create') == 'project'

    @staticmethod
    async def is_project_owner(db, project_id, actor_id):
        return bool(await db.scalar(text("""SELECT EXISTS(
            SELECT 1 FROM hf_project p JOIN hf_project_member m USING(project_id)
            JOIN hf_project_role r USING(role_id)
            WHERE p.project_id=:project AND p.owner_user_id=:actor AND p.del_flag='0'
            AND m.user_id=:actor AND m.status='0' AND r.code='owner')"""),
            {'project': project_id, 'actor': actor_id}))

"""按实际授予功能码的有效角色计算管理范围；只使用 PostgreSQL 查询。"""

from sqlalchemy import text


class AdminScopeDao:
    @staticmethod
    async def actor(db, user_id):
        return (
            (
                await db.execute(
                    text("SELECT user_id,dept_id FROM sys_user WHERE user_id=:id AND status='0' AND del_flag='0'"),
                    {'id': user_id},
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    async def scopes(db, user_id, permission):
        return (
            (
                await db.execute(
                    text("""
            SELECT DISTINCT r.role_id,r.data_scope
            FROM sys_user_role ur JOIN sys_role r ON r.role_id=ur.role_id
            JOIN sys_role_menu rm ON rm.role_id=r.role_id
            JOIN sys_menu m ON m.menu_id=rm.menu_id
            WHERE ur.user_id=:actor AND r.status='0' AND r.del_flag='0'
              AND m.status='0' AND m.perms=:permission
        """),
                    {'actor': user_id, 'permission': permission},
                )
            )
            .mappings()
            .all()
        )

    @staticmethod
    async def project(db, project_id, lock=False):
        return (
            (
                await db.execute(
                    text(
                        """
            SELECT p.project_id,p.create_user_id,p.status,p.del_flag,u.dept_id
            FROM hf_project p LEFT JOIN sys_user u ON u.user_id=p.create_user_id
            WHERE p.project_id=:id
        """
                        + (' FOR UPDATE OF p' if lock else '')
                    ),
                    {'id': project_id},
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    async def custom_department(db, role_ids, dept_id):
        return bool(
            await db.scalar(
                text("""
            SELECT EXISTS(SELECT 1 FROM sys_role_dept rd JOIN sys_dept d ON d.dept_id=rd.dept_id
              WHERE rd.role_id=ANY(CAST(:roles AS bigint[])) AND rd.dept_id=:dept
                AND d.status='0' AND d.del_flag='0')
        """),
                {'roles': role_ids, 'dept': dept_id},
            )
        )

    @staticmethod
    async def department_contains(db, source_id, target_id, include_children):
        return bool(
            await db.scalar(
                text("""
            SELECT EXISTS(SELECT 1 FROM sys_dept source JOIN sys_dept target ON target.dept_id=:target
              WHERE source.dept_id=:source AND source.status='0' AND source.del_flag='0'
                AND target.status='0' AND target.del_flag='0'
                AND (target.dept_id=source.dept_id OR (:children AND
                     CAST(source.dept_id AS text)=ANY(string_to_array(target.ancestors,',')))))
        """),
                {'source': source_id, 'target': target_id, 'children': include_children},
            )
        )

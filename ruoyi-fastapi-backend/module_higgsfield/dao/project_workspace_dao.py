from hashlib import sha256

from sqlalchemy import func, select, text

from module_higgsfield.entity.do.project_do import (
    HfApiIdempotencyRecord,
    HfProject,
    HfProjectBrief,
    HfProjectMember,
    HfProjectRole,
    HfProjectRolePermission,
)


class WorkspaceDao:
    """项目工作区查询；写事务由服务层统一提交。"""

    @staticmethod
    async def lock_request(db, user_id, path, key, api_prefix='/api/v1'):
        lock_id = int.from_bytes(sha256(f'{user_id}:{api_prefix}:{path}:{key}'.encode()).digest()[:8], signed=True)
        return await db.scalar(select(func.pg_try_advisory_xact_lock(lock_id)))

    @staticmethod
    async def lock_project(db, project_id):
        return await db.scalar(select(HfProject).where(HfProject.project_id == project_id).with_for_update())

    @staticmethod
    async def permissions(db, role_code):
        return set(
            (
                await db.scalars(
                    select(HfProjectRolePermission.permission_code)
                    .join(HfProjectRole, HfProjectRole.role_id == HfProjectRolePermission.role_id)
                    .where(HfProjectRole.code == role_code, HfProjectRolePermission.data_scope == 'project')
                )
            ).all()
        )

    @staticmethod
    async def permission_scopes(db, role_code, project_id=None):
        from module_higgsfield.project_permissions import OWNER_PERMISSIONS
        if role_code == 'owner':
            return dict.fromkeys(OWNER_PERMISSIONS, 'project')
        hierarchy = ['viewer', 'producer', 'admin']
        if role_code not in hierarchy:
            return {}
        roles = hierarchy[:hierarchy.index(role_code) + 1]
        rows = (await db.execute(
            select(HfProjectRole.code, HfProjectRolePermission.permission_code,
                   HfProjectRolePermission.data_scope)
            .join(HfProjectRole, HfProjectRole.role_id == HfProjectRolePermission.role_id)
            .where(HfProjectRole.code.in_(roles))
        )).all()
        values = {role: {} for role in roles}
        for role, code, scope in rows:
            values[role][code] = scope
        if project_id is not None:
            from module_higgsfield.dao.project_permission_dao import ProjectPermissionDao
            config = await ProjectPermissionDao.get(db, project_id)
            for role in roles:
                values[role].update(config.overrides.get(role, {}) if config else {})
        # 高级角色继承低级角色的有效权限，范围不得缩小；旧自定义配置同样适用。
        scopes = {}
        for role in roles:
            for code, scope in values[role].items():
                if code not in OWNER_PERMISSIONS or scope == 'none':
                    continue
                if scope == 'project' or code not in scopes:
                    scopes[code] = scope
        return scopes

    @staticmethod
    async def brief(db, project_id):
        return await db.scalar(select(HfProjectBrief).where(HfProjectBrief.project_id == project_id))

    @staticmethod
    async def member(db, project_id, user_id):
        return await db.scalar(
            select(HfProjectMember).where(HfProjectMember.project_id == project_id, HfProjectMember.user_id == user_id)
        )

    @staticmethod
    async def members(db, project_id, query):
        condition = (
            HfProjectMember.project_id == project_id,
            HfProjectMember.user_id != 1,
            HfProjectMember.status == ('0' if query.status == 'active' else '1'),
        )
        count = await db.scalar(select(func.count()).select_from(HfProjectMember).where(*condition))
        rows = (
            await db.scalars(
                select(HfProjectMember)
                .where(*condition)
                .order_by(HfProjectMember.member_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, count

    @staticmethod
    async def user(db, user_id, lock=False):
        suffix = ' FOR SHARE' if lock else ''
        return (
            (
                await db.execute(
                    text('SELECT user_id,user_name,nick_name,status,del_flag FROM sys_user WHERE user_id=:id' + suffix),
                    {'id': user_id},
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    async def find_user(db, account):
        # 精确账号查询，不提供全公司用户目录或联系方式。
        return (
            (
                await db.execute(
                    text(
                        'SELECT user_id,nick_name,user_name FROM sys_user '
                        "WHERE user_id<>1 AND user_name=:name AND status='0' AND del_flag='0'"
                    ),
                    {'name': account},
                )
            )
            .mappings()
            .first()
        )

    @staticmethod
    async def eligible_users(db, project_id, keyword='', page=1, size=20, user_id=None):
        """只返回有效制作平台使用者；使用 EXISTS 避免多角色造成重复。"""
        conditions = """u.user_id <> 1 AND u.status='0' AND u.del_flag='0'
            AND EXISTS (SELECT 1 FROM sys_user_role ur JOIN sys_role r ON r.role_id=ur.role_id
                WHERE ur.user_id=u.user_id AND r.role_key='hf_studio_user'
                AND r.status='0' AND r.del_flag='0')
            AND (:keyword='' OR strpos(lower(u.user_name), lower(:keyword))>0
                OR strpos(lower(coalesce(u.nick_name,'')), lower(:keyword))>0)"""
        params = {'keyword': keyword, 'project': project_id, 'limit': size, 'offset': (page-1)*size}
        if user_id is not None:
            conditions += ' AND u.user_id=:user_id'
            params['user_id'] = user_id
        total = await db.scalar(text('SELECT count(*) FROM sys_user u WHERE ' + conditions), params)
        rows = (await db.execute(text("""SELECT u.user_id,u.user_name,u.nick_name,
            EXISTS(SELECT 1 FROM hf_project_member m WHERE m.project_id=:project
                AND m.user_id=u.user_id AND m.status='0') AS already_member
            FROM sys_user u WHERE """ + conditions + ' ORDER BY u.user_name,u.user_id LIMIT :limit OFFSET :offset'), params)).mappings().all()
        return rows, total

    @staticmethod
    async def roles(db):
        return (await db.scalars(select(HfProjectRole).order_by(HfProjectRole.role_id))).all()

    @staticmethod
    async def owner_count(db, project_id):
        return await db.scalar(
            select(func.count())
            .select_from(HfProjectMember)
            .join(HfProjectRole, HfProjectRole.role_id == HfProjectMember.role_id)
            .where(
                HfProjectMember.project_id == project_id, HfProjectMember.status == '0', HfProjectRole.code == 'owner'
            )
        )

    @staticmethod
    async def replay(db, actor_id, method, path, key, api_prefix='/api/v1'):
        return await db.scalar(
            select(HfApiIdempotencyRecord).where(
                HfApiIdempotencyRecord.actor_id == actor_id,
                HfApiIdempotencyRecord.api_prefix == api_prefix,
                HfApiIdempotencyRecord.http_method == method,
                HfApiIdempotencyRecord.normalized_path == path,
                HfApiIdempotencyRecord.idempotency_key == key,
            )
        )

    @staticmethod
    async def flush(db):
        await db.flush()

    @staticmethod
    def add_member(db, **values):
        member = HfProjectMember(**values)
        db.add(member)
        return member

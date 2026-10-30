"""固定项目角色的权限矩阵，授权变更限定到当前项目。"""
from exceptions.exception import PermissionException
from module_higgsfield.dao.project_permission_dao import ProjectPermissionDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService

# 读取及治理基础权限固定；可写内容权限沿用各对象服务的范围校验。
CATALOG = [
    ('查看', 'project:read', '查看项目', False, False),
    ('查看', 'member:read', '查看成员', False, False),
    ('查看', 'asset:read', '查看素材', True, False),
    ('查看', 'element:read', '查看元素', True, False),
    ('查看', 'generation:read', '查看生成记录', False, False),
    ('内容操作', 'generation:create', '生成内容', True, False),
    ('内容操作', 'generation:cancel', '取消生成任务', True, True),
    ('内容操作', 'asset:upload', '上传素材', True, False),
    ('内容操作', 'asset:create', '创建素材', True, False),
    ('内容操作', 'asset:reference', '引用素材', True, False),
    ('内容操作', 'asset:edit', '编辑素材', True, True),
    ('内容操作', 'asset:remove', '移除与恢复素材', True, True),
    ('内容操作', 'asset:download', '下载素材', True, False),
    ('内容操作', 'element:create', '创建元素', True, False),
    ('内容操作', 'element:edit', '编辑元素', True, True),
    ('内容操作', 'element:remove', '移除与恢复元素', True, True),
    ('内容操作', 'element:configure', '配置元素属性', True, True),
    ('内容操作', 'element:copy', '跨项目复制元素', True, False),
    ('内容操作', 'element:import', '导入元素', True, False),
    ('内容操作', 'folder:write', '管理项目目录', True, False),
    ('内容操作', 'content:review', '审核内容状态', True, True),
    ('内容操作', 'output:archive', '重试作品归档', True, True),
    ('评论', 'comment:read', '查看评论', True, False),
    ('评论', 'comment:create', '发表评论', True, False),
    ('评论', 'comment:edit:own', '编辑本人评论', True, False),
    ('评论', 'comment:moderate', '管理项目评论', True, False),
    ('项目管理', 'project:edit', '编辑项目简报', True, False),
    ('项目管理', 'member:manage', '管理成员与角色', False, False),
    ('项目管理', 'project:manage', '管理项目基本信息', False, False),
    ('项目管理', 'project:archive', '归档和恢复项目', False, False),
]


class ProjectPermissionService:
    @staticmethod
    async def read(db, user, project_id):
        project, role, allowed = await WorkspaceService.authorize(db, user, project_id, 'member:read')
        config = await ProjectPermissionDao.get(db, project_id)
        roles = []
        for item in await WorkspaceDao.roles(db):
            if item.code not in ('owner', 'admin', 'producer', 'viewer'):
                continue
            defaults = await WorkspaceDao.permission_scopes(db, item.code)
            current = await WorkspaceDao.permission_scopes(db, item.code, project_id)
            roles.append({'code': item.code, 'name': item.role_name, 'defaults': defaults, 'permissions': current})
        return {'revision': str(config.revision) if config else '0', 'roles': sorted(roles, key=lambda item: ['owner', 'admin', 'producer', 'viewer'].index(item['code'])),
                'canEdit': role == 'owner' and 'member:manage' in allowed and project.status == '0',
                'rows': [{'group': group, 'code': code, 'label': label, 'scoped': scoped,
                          'editable': editable and (role == 'owner' or code in user.permissions or '*:*:*' in user.permissions)}
                         for group, code, label, editable, scoped in CATALOG]}

    @staticmethod
    def validate(overrides, permissions):
        editable = {code: scoped for _, code, _, enabled, scoped in CATALOG if enabled}
        if set(overrides) - {'admin', 'producer', 'viewer'}:
            raise PermissionException(message='不支持的项目角色')
        for values in overrides.values():
            for code, scope in values.items():
                if code not in editable or (scope == 'own' and not editable[code]):
                    raise PermissionException(message='不能修改此权限或范围')
                if code not in permissions and '*:*:*' not in permissions:
                    raise PermissionException(message='不能配置超出本人系统授权的权限')

    @classmethod
    async def save(cls, db, user, project_id, payload, key):
        path = f'/projects/{project_id}/role-permissions'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            _, role, _ = await WorkspaceService.authorize(db, user, project_id, 'member:manage', write=True)
            if role != 'owner':
                raise PermissionException(message='仅 Owner 可配置角色权限')
            replay = await WriteService.replay(db, user, path, key, data, method='PUT')
            if replay:
                await db.commit()
                return replay, True
            config = await ProjectPermissionDao.get(db, project_id)
            if str(config.revision if config else 0) != payload.revision:
                WorkspaceService.conflict('REVISION_CONFLICT', '权限已被其他请求修改，请重新加载后再保存')
            cls.validate(payload.overrides, ['*:*:*'])
            # 请求按可配置项合并；无系统授权的既有配置不由当前用户覆盖。
            merged = {role: dict(values) for role, values in (config.overrides if config else {}).items()}
            for role, values in payload.overrides.items():
                merged.setdefault(role, {}).update(values)
            await ProjectPermissionDao.save(db, project_id, config, merged, WriteService.audit(user))
            result = await cls.read(db, user, project_id)
            return await WriteService.finish(db, user, path, key, data, result, 'project_permissions', project_id, method='PUT')
        except Exception:
            await db.rollback()
            raise

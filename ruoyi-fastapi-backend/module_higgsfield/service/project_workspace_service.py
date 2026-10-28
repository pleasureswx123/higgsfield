import json
from datetime import timedelta
from hashlib import sha256

from common.vo import PageModel
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from utils.response_util import ResponseUtil
from utils.time_util import TimezoneUtil


class WorkspaceService:
    """每次请求实时读取成员权限；撤权不依赖缓存或前端状态。"""

    @staticmethod
    def conflict(code, message):
        raise ServiceWarning(message=message, data={'errorCode': code})

    @classmethod
    async def authorize(cls, db, user, project_id, permission, write=False, owner_id=None):
        if write:
            await WorkspaceDao.lock_project(db, project_id)
        row = await ProjectDao.get_project(db, user.user.user_id, project_id)
        if row is None:
            cls.conflict('RESOURCE_NOT_FOUND', '项目不存在或无权访问')
        scopes = await WorkspaceDao.permission_scopes(db, row[1])
        permissions = {
            code
            for code, scope in scopes.items()
            if scope == 'project' or (scope == 'own' and owner_id == user.user.user_id)
        }
        allowed = permissions.intersection(user.permissions) if '*:*:*' not in user.permissions else permissions
        if permission not in allowed:
            raise PermissionException(message='没有执行此项目操作的权限')
        if write and row[0].status != '0':
            cls.conflict('PROJECT_READ_ONLY', '暂停、归档或待删除项目不可修改')
        return row[0], row[1], allowed

    @staticmethod
    def brief_result(brief, allowed):
        return {
            'projectId': str(brief.project_id),
            'body': brief.body,
            'revision': str(brief.revision),
            'updateTime': brief.update_time,
            'allowedActions': sorted(allowed),
        }

    @classmethod
    async def get_brief(cls, db, user, project_id):
        project, _, allowed = await cls.authorize(db, user, project_id, 'project:read')
        if project.status != '0':
            allowed = allowed - {
                'project:edit',
                'member:manage',
                'folder:write',
                'asset:upload',
                'asset:create',
                'asset:edit',
                'asset:remove',
                'element:create',
                'element:edit',
                'element:remove',
                'element:configure',
                'content:review',
            }
        # 暂停态保留治理入口供恢复运行；归档及待删除态不提供普通管理动作。
        if project.status in {'2', '3'}:
            allowed = allowed - {'project:manage'}
        return cls.brief_result(await WorkspaceDao.brief(db, project_id), allowed)

    @classmethod
    async def member_result(cls, db, member):
        user = await WorkspaceDao.user(db, member.user_id)
        return {
            'userId': str(member.user_id),
            'displayName': (user['nick_name'] or user['user_name']) if user else '已删除用户',
            'roleId': str(member.role_id),
            'status': 'active' if member.status == '0' else 'removed',
            'revision': str(member.revision),
            'joinedAt': member.joined_time,
        }

    @classmethod
    async def list_members(cls, db, user, project_id, query):
        await cls.authorize(db, user, project_id, 'member:read')
        members, count = await WorkspaceDao.members(db, project_id, query)
        return PageModel(
            rows=[await cls.member_result(db, member) for member in members],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=count,
            hasNext=query.page_num * query.page_size < count,
        )

    @classmethod
    async def roles(cls, db, user, project_id):
        _, role, allowed = await cls.authorize(db, user, project_id, 'member:read')
        result = []
        for item in await WorkspaceDao.roles(db):
            result.append(
                {
                    'id': str(item.role_id),
                    'code': item.code,
                    'name': item.role_name,
                    'permissions': sorted(await WorkspaceDao.permissions(db, item.code)),
                    'canGrant': role == 'owner'
                    and 'member:manage' in allowed
                    and item.code in ('owner', 'producer', 'viewer'),
                }
            )
        return {'items': result}

    @classmethod
    async def candidate(cls, db, user, project_id, account):
        await cls.authorize(db, user, project_id, 'member:manage', write=True)
        candidate = await WorkspaceDao.find_user(db, account.strip())
        return {
            'items': [
                {'userId': str(candidate['user_id']), 'displayName': candidate['nick_name'] or candidate['user_name']}
            ]
            if candidate
            else []
        }

    @classmethod
    async def grant_member(cls, db, user, project_id, target_id, role_id, actor_role):
        """调用方须已锁定并授权项目；复用授予规则，不提交事务。"""
        if actor_role != 'owner':
            raise PermissionException(message='仅项目负责人可以授予成员角色')
        role = next((item for item in await WorkspaceDao.roles(db) if item.role_id == int(role_id)), None)
        if role is None or role.code not in ('owner', 'producer', 'viewer'):
            raise PermissionException(message='不能授予此项目角色')
        target = await WorkspaceDao.user(db, target_id, lock=True)
        if target is None or target['status'] != '0' or target['del_flag'] != '0':
            cls.conflict('USER_UNAVAILABLE', '用户不存在或已停用')
        member = await WorkspaceDao.member(db, project_id, target_id)
        if member and member.status == '0':
            cls.conflict('MEMBER_EXISTS', '该用户已经是项目成员')
        now = TimezoneUtil.utc_now()
        if member:
            member.role_id, member.status, member.removed_time = role.role_id, '0', None
            member.joined_time, member.revision = now, member.revision + 1
        else:
            member = WorkspaceDao.add_member(db, project_id=project_id, user_id=target_id,
                role_id=role.role_id, status='0', revision=1, joined_time=now,
                create_by=user.user.user_name, create_time=now)
        member.update_by, member.update_time = user.user.user_name, now
        await WorkspaceDao.flush(db)
        return member

    @classmethod
    async def mutate(cls, db, user, project_id, action, payload, key=None, user_id=None):
        permission = 'project:edit' if action == 'brief' else 'member:manage'
        method = {'brief': 'PUT', 'add': 'POST', 'role': 'PATCH', 'remove': 'DELETE'}[action]
        path = (
            f'/projects/{project_id}/brief'
            if action == 'brief'
            else f'/projects/{project_id}/members' + (f'/{user_id}' if user_id else '')
        )
        digest = sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        ).hexdigest()
        try:
            project, actor_role, allowed = await cls.authorize(db, user, project_id, permission, write=True)
            if key:
                replay = await WorkspaceDao.replay(db, user.user.user_id, method, path, key)
                if replay:
                    if replay.request_hash != digest:
                        cls.conflict('IDEMPOTENCY_KEY_REUSED', '请求标识已用于其他内容')
                    if replay.state != '1':
                        cls.conflict('IDEMPOTENCY_IN_PROGRESS', '请求尚未完成')
                    await db.commit()
                    return replay.safe_result, True
            now = TimezoneUtil.utc_now()
            if action == 'brief':
                brief = await WorkspaceDao.brief(db, project_id)
                cls.check_revision(brief, payload['revision'])
                brief.body = payload['body']
                brief.revision += 1
                brief.update_user_id = user.user.user_id
                brief.update_by, brief.update_time = user.user.user_name, now
                result = cls.brief_result(brief, allowed)
            else:
                if actor_role != 'owner':
                    raise PermissionException(message='仅项目负责人可以授予或移除成员角色')
                target_id = int(payload['userId']) if action == 'add' else user_id
                member = await WorkspaceDao.member(db, project_id, target_id)
                roles = {item.role_id: item for item in await WorkspaceDao.roles(db)}
                role = roles.get(int(payload['roleId'])) if action != 'remove' else None
                if action != 'remove' and (role is None or role.code not in ('owner', 'producer', 'viewer')):
                    raise PermissionException(message='不能授予此项目角色')
                if action == 'add':
                    member = await cls.grant_member(db, user, project_id, target_id, payload['roleId'], actor_role)
                else:
                    if member is None or member.status != '0':
                        cls.conflict('RESOURCE_NOT_FOUND', '成员不存在或已移除')
                    cls.check_revision(member, payload['revision'])
                    if roles[member.role_id].code == 'owner' and (action == 'remove' or role.code != 'owner'):
                        if await WorkspaceDao.owner_count(db, project_id) <= 1:
                            cls.conflict('LAST_OWNER', '必须保留至少一位项目负责人')
                    if action == 'remove':
                        member.status, member.removed_time = '1', now
                    else:
                        member.role_id = role.role_id
                    member.revision += 1
                member.update_by, member.update_time = user.user.user_name, now
                await WorkspaceDao.flush(db)
                result = await cls.member_result(db, member)
            project.update_by, project.update_time = user.user.user_name, now
            project.revision += 1
            await WorkspaceDao.flush(db)
            response = json.loads(ResponseUtil.success(data=result).body)
            if key:
                await ProjectDao.save_idempotency(
                    db,
                    actor_id=user.user.user_id,
                    api_prefix='/api/v1',
                    http_method=method,
                    normalized_path=path,
                    idempotency_key=key,
                    request_hash=digest,
                    state='1',
                    http_status=200,
                    result_type='project',
                    result_id=str(project_id),
                    safe_result=response,
                    expires_time=now + timedelta(days=1),
                    completed_time=now,
                    fencing_token=1,
                    create_by=user.user.user_name,
                    update_by=user.user.user_name,
                    create_time=now,
                    update_time=now,
                )
            await db.commit()
            return response, False
        except Exception:
            await db.rollback()
            raise

    @classmethod
    def check_revision(cls, entity, revision):
        if str(entity.revision) != revision:
            cls.conflict('REVISION_CONFLICT', '内容已被其他人更新，请先重新加载；你的草稿已保留')

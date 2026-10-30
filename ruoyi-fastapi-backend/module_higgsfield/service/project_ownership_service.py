"""所有权在项目锁下原子转让，保留创建者和审计证据。"""
from exceptions.exception import PermissionException
from module_higgsfield.dao.generation_actor_dao import GenerationActorDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ProjectOwnershipService:
    @staticmethod
    async def transfer(db, user, project_id, payload, key):
        path = f'/projects/{project_id}/ownership'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            project, actor_role, _ = await WorkspaceService.authorize(db, user, project_id, 'project:read', write=True)
            replay = await WriteService.replay(db, user, path, key, data, method='PUT')
            if replay:
                await db.commit()
                return replay, True
            if actor_role != 'owner' or project.owner_user_id != user.user.user_id:
                raise PermissionException(message='仅当前Owner可转让项目所有权')
            target_id = int(payload.user_id)
            if target_id == user.user.user_id:
                WorkspaceService.conflict('SAME_OWNER', '请选择其他项目成员')
            target_user = await WorkspaceDao.user(db, target_id, lock=True)
            if not target_user or target_user['status'] != '0' or target_user['del_flag'] != '0':
                WorkspaceService.conflict('USER_UNAVAILABLE', '接收人已停用或不存在')
            if not await GenerationActorDao.system_access(db, target_id, 'project:read'):
                WorkspaceService.conflict('STUDIO_ACCESS_REQUIRED', '接收人未获制作平台项目访问授权，请先分配制作平台使用者角色')
            previous = await WorkspaceDao.member(db, project_id, user.user.user_id)
            target = await WorkspaceDao.member(db, project_id, target_id)
            if target is None or target.status != '0':
                WorkspaceService.conflict('MEMBER_REQUIRED', '接收人必须是当前项目成员')
            WorkspaceService.check_revision(project, payload.revision)
            WorkspaceService.check_revision(target, payload.target_revision)
            roles = {role.code: role.role_id for role in await WorkspaceDao.roles(db)}
            audit = WriteService.audit(user)
            previous.role_id = roles['admin']
            previous.revision += 1
            previous.update_by, previous.update_time = audit['update_by'], audit['update_time']
            # 先降级旧Owner，满足唯一Owner索引，整个事务提交前外部不可见。
            await WorkspaceDao.flush(db)
            target.role_id = roles['owner']
            target.revision += 1
            target.update_by, target.update_time = audit['update_by'], audit['update_time']
            project.owner_user_id = target_id
            project.revision += 1
            project.update_by, project.update_time = audit['update_by'], audit['update_time']
            await WorkspaceDao.flush(db)
            result = {'projectId': str(project_id), 'previousOwnerId': str(user.user.user_id), 'ownerUserId': str(target_id)}
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user', project_id=project_id,
                object_type='project_ownership', object_id=str(project_id), action='transfer', reason='Owner转让项目所有权',
                request_id=WriteService.digest({'path': path, 'key': key}), before_after=result, **audit))
            return await WriteService.finish(db, user, path, key, data, result, 'project_ownership', project_id, method='PUT')
        except Exception:
            await db.rollback()
            raise

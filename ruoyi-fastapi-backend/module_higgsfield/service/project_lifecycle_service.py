"""制作端项目改名、归档与恢复：成员授权、审计和幂等同事务。"""
from module_higgsfield.dao.project_governance_dao import ProjectGovernanceDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ProjectLifecycleService:
    @staticmethod
    async def change(db, user, identity, action, payload, key):
        if action not in {'archive', 'restore', 'rename', 'pause', 'resume'}:
            raise ValueError('不支持的项目生命周期操作')
        path = f'/projects/{identity}' if action == 'rename' else f'/projects/{identity}/{action}'
        method = 'PATCH' if action == 'rename' else 'POST'
        permission = 'project:archive' if action in {'archive', 'restore'} else 'project:manage'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await WorkspaceService.authorize(db, user, identity, permission)
            await WriteService.lock(db, user, path, key)
            await ProjectGovernanceDao.locked(db, identity)
            # 恢复允许归档态，但仍须锁后重验当前成员与功能权限。
            project, role, _ = await WorkspaceService.authorize(db, user, identity, permission)
            replay = await WriteService.replay(db, user, path, key, data, method=method)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(project, payload.revision)
            sources = {'archive': {'0', '1'}, 'restore': {'2'}, 'rename': {'0'}, 'pause': {'0'}, 'resume': {'1'}}
            if project.status not in sources[action]:
                WorkspaceService.conflict('PROJECT_LIFECYCLE_STATE_INVALID', '当前项目状态不允许此操作')
            before = ProjectService.project_model(project, role).model_dump(by_alias=True, mode='json')
            audit = WriteService.audit(user)
            if action == 'rename':
                project.project_name = payload.name
            else:
                project.status = {'archive': '2', 'restore': '0', 'pause': '1', 'resume': '0'}[action]
                project.archived_time = audit['update_time'] if action == 'archive' else None
            project.revision += 1
            project.update_by, project.update_time = audit['update_by'], audit['update_time']
            after = ProjectService.project_model(project, role).model_dump(by_alias=True, mode='json')
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user',
                project_id=identity, object_type='project', object_id=str(identity), action=action,
                reason=payload.reason if action != 'rename' else None,
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': after}, **audit))
            return await WriteService.finish(db, user, path, key, data, after, 'project', identity, method=method)
        except Exception:
            await db.rollback()
            raise

"""制作端项目改名、归档与恢复：成员授权、审计和幂等同事务。"""
from exceptions.exception import PermissionException
from module_higgsfield.dao.budget_dao import BudgetDao
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_governance_dao import ProjectGovernanceDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ProjectLifecycleService:
    @staticmethod
    async def change(db, user, identity, action, payload, key):
        if action not in {'archive', 'restore', 'rename', 'pause', 'resume', 'delete'}:
            raise ValueError('不支持的项目生命周期操作')
        path = f'/projects/{identity}' if action == 'rename' else f'/projects/{identity}/{action}'
        method = 'PATCH' if action == 'rename' else 'POST'
        permission = 'project:archive' if action in {'archive', 'restore'} else 'project:manage'
        if action == 'delete':
            permission = 'project:read'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            if action != 'delete':
                await WorkspaceService.authorize(db, user, identity, permission)
            await WriteService.lock(db, user, path, key)
            if action == 'delete':
                # 成功删除后普通项目查询不可见，按操作者、路径和请求键重放原回执。
                replay = await WriteService.replay(db, user, path, key, data)
                if replay:
                    await db.commit()
                    return replay, True
                _, role, _ = await WorkspaceService.authorize(db, user, identity, permission)
                if role != 'owner':
                    raise PermissionException(message='只有项目 Owner 可以删除空项目')
            await ProjectGovernanceDao.locked(db, identity)
            # 恢复允许归档态，但仍须锁后重验当前成员与功能权限。
            project, role, _ = await WorkspaceService.authorize(db, user, identity, permission)
            if action != 'delete':
                replay = await WriteService.replay(db, user, path, key, data, method=method)
                if replay:
                    await db.commit()
                    return replay, True
            else:
                if role != 'owner' or project.owner_user_id != user.user.user_id:
                    raise PermissionException(message='只有项目 Owner 可以删除空项目')
                await BudgetDao.lock_subject(db, 'project', identity)
                blockers = await ProjectDao.deletion_blockers(db, identity, project.owner_user_id)
                if blockers:
                    hint = '请保留归档状态' if project.status == '2' else '请改用归档项目'
                    WorkspaceService.conflict('PROJECT_NOT_EMPTY', f"项目已有{'、'.join(blockers)}，{hint}。")
            WorkspaceService.check_revision(project, payload.revision)
            sources = {'archive': {'0', '1'}, 'restore': {'2'}, 'rename': {'0'}, 'pause': {'0'}, 'resume': {'1'}, 'delete': {'0', '1', '2'}}
            if project.status not in sources[action]:
                WorkspaceService.conflict('PROJECT_LIFECYCLE_STATE_INVALID', '当前项目状态不允许此操作')
            before = ProjectService.project_model(project, role).model_dump(by_alias=True, mode='json')
            audit = WriteService.audit(user)
            if action == 'delete':
                project.del_flag = '2'
            elif action == 'rename':
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
                before_after={'before': before, 'after': {**after, 'delFlag': '2'} if action == 'delete' else after}, **audit))
            return await WriteService.finish(db, user, path, key, data, after, 'project', identity, method=method)
        except Exception:
            await db.rollback()
            raise

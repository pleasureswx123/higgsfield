"""素材身份变更与回收证据；归档文件和历史版本始终保留。"""

from datetime import timedelta
from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.do.folder_do import HfRecycleEntry
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


class AssetLifecycleService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    async def trash(cls, db, user, project_id, page_num, page_size):
        project, role, _ = await WorkspaceService.authorize(db, user, project_id, 'project:read')
        scopes = await WorkspaceDao.permission_scopes(db, role)
        scope = scopes.get('asset:remove')
        if scope is None or ('*:*:*' not in user.permissions and 'asset:remove' not in user.permissions):
            raise PermissionException(message='没有查看素材回收站的权限')
        rows, total = await AssetDao.trash(
            db, project_id, user.user.user_id if scope == 'own' else None, page_num, page_size
        )
        now = TimezoneUtil.utc_now()
        return PageModel(
            rows=[
                {
                    'id': str(recycle.recycle_id),
                    'projectId': str(project_id),
                    'targetKind': 'asset',
                    'targetId': str(asset.asset_id),
                    'name': asset.asset_name,
                    'revision': str(asset.revision),
                    'deletedTime': recycle.deleted_time,
                    'restoreUntil': recycle.restore_until,
                    'canRestore': project.status == '0' and recycle.restore_until > now,
                    'originalParentId': str(recycle.original_parent_id) if recycle.original_parent_id else None,
                }
                for recycle, asset in rows
            ],
            total=total,
            pageNum=page_num,
            pageSize=page_size,
            hasNext=page_num * page_size < total,
        )

    @classmethod
    async def mutate(cls, db, user, asset_id, action, payload, key):
        path = f'/assets/{asset_id}' + ('/restore' if action == 'restore' else '/status' if action == 'status' else '')
        method = {'status': 'PATCH', 'rename': 'PATCH', 'delete': 'DELETE', 'restore': 'POST'}[action]
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            project_id = await AssetDao.project_id(db, asset_id)
            if project_id is None:
                cls.fail('RESOURCE_NOT_FOUND', '素材不存在或无权访问')
            asset = await AssetDao.asset(db, asset_id)
            await WorkspaceService.authorize(
                db,
                user,
                project_id,
                'content:review' if action == 'status' else 'asset:edit' if action == 'rename' else 'asset:remove',
                write=True,
                owner_id=asset.create_user_id,
            )
            asset = await AssetDao.asset(db, asset_id)
            await FolderDao.space(db, project_id, lock=True)
            replay = await WriteService.replay(db, user, path, key, data, method)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(asset, payload.revision)
            entry = await AssetDao.asset_entry(db, asset_id)
            if entry is None:
                cls.fail('RESOURCE_NOT_FOUND', '素材目录归属不存在')
            now = TimezoneUtil.utc_now()
            if action == 'restore':
                recycle = await AssetDao.recycle(db, asset_id)
                if asset.del_flag != '2' or recycle is None:
                    cls.fail('RESOURCE_NOT_REMOVED', '素材不在回收站中')
                if recycle.restore_until <= now:
                    cls.fail('RESTORE_EXPIRED', '自助恢复期限已过，请联系项目管理员')
                parent_id = recycle.original_parent_id
                if parent_id is not None:
                    parent = await FolderDao.get(db, parent_id)
                    if (
                        parent is None
                        or parent.del_flag != '0'
                        or parent.space_id != asset.space_id
                        or parent.folder_kind != 'media'
                    ):
                        cls.fail('RESTORE_PARENT_UNAVAILABLE', '原素材目录不可用，请先恢复目录')
                await FolderService.check_target(db, asset.space_id, parent_id, 'media')
                asset.del_flag, entry.folder_id = '0', parent_id
                entry.revision += 1
                entry.update_by, entry.update_time = user.user.user_name, now
                recycle.state, recycle.restored_time, recycle.restored_by = 'restored', now, user.user.user_id
                recycle.revision += 1
                recycle.update_by, recycle.update_time = user.user.user_name, now
            else:
                if asset.del_flag != '0':
                    cls.fail('RESOURCE_REMOVED', '素材已在回收站中')
                if action == 'rename':
                    asset.asset_name = payload.name
                elif action == 'status':
                    asset.work_status = payload.work_status
                else:
                    await AssetDao.add(
                        db,
                        HfRecycleEntry,
                        project_id=project_id,
                        target_kind='asset',
                        target_id=asset_id,
                        original_parent_id=entry.folder_id,
                        deleted_time=now,
                        restore_until=now + timedelta(days=30),
                        actor_id=user.user.user_id,
                        state='active',
                        revision=1,
                        snapshot={'name': asset.asset_name, 'currentVersionId': str(asset.current_version_id)},
                        **WriteService.audit(user),
                    )
                    asset.del_flag = '2'
            asset.revision += 1
            asset.update_by, asset.update_time = user.user.user_name, now
            await AssetDao.flush(db)
            return await WriteService.finish(
                db, user, path, key, data, await AssetService.result(db, asset), 'asset', asset_id, method
            )
        except Exception:
            await db.rollback()
            raise

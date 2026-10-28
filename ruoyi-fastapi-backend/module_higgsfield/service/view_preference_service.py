"""视图偏好保存白名单数据，每次访问重新验证项目范围。"""
from pydantic import ValidationError
from module_higgsfield.dao.view_preference_dao import ViewPreferenceDao
from module_higgsfield.dao.project_preference_dao import PreferenceDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.vo.view_preference_vo import normalize_settings
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ViewPreferenceService:
    @staticmethod
    def result(view_key, project_id, row):
        return dict(viewKey=view_key, projectId=str(project_id) if project_id else None,
                    settings=row.settings if row else normalize_settings(view_key, {}),
                    revision=str(row.revision) if row else '0')

    @staticmethod
    async def authorize(db, user, view_key, project_id, write=False):
        if view_key == 'projects' and project_id is not None:
            WorkspaceService.conflict('INVALID_VIEW_SCOPE', '项目列表偏好仅支持全局范围')
        if project_id is not None:
            if write:
                await WorkspaceDao.lock_project(db, project_id)
            await WorkspaceService.authorize(db, user, project_id, 'project:read')

    @classmethod
    async def get(cls, db, user, view_key, project_id=None):
        await cls.authorize(db, user, view_key, project_id)
        return cls.result(view_key, project_id, await ViewPreferenceDao.get(db, user.user.user_id, view_key, project_id))

    @classmethod
    async def put(cls, db, user, view_key, payload, key):
        project_id = int(payload.project_id) if payload.project_id else None
        path = f'/view-preferences/{view_key}'
        raw = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            await cls.authorize(db, user, view_key, project_id, True)
            await PreferenceDao.lock_user(db, user.user.user_id)
            replay = await WriteService.replay(db, user, path, key, raw, 'PUT')
            if replay:
                await db.commit()
                return replay, True
            try:
                settings = normalize_settings(view_key, payload.settings)
            except ValidationError:
                WorkspaceService.conflict('INVALID_VIEW_SETTINGS', '视图设置包含未知字段或无效值')
            if view_key == 'projects' and settings['collectionId'] is not None:
                if not await PreferenceDao.collection(db, user.user.user_id, int(settings['collectionId']), True):
                    WorkspaceService.conflict('RESOURCE_NOT_FOUND', '集合不存在或不属于本人')
            row = await ViewPreferenceDao.get(db, user.user.user_id, view_key, project_id, True)
            if payload.revision != (str(row.revision) if row else '0'):
                WorkspaceService.conflict('REVISION_CONFLICT', '视图偏好已更新，请重新读取')
            audit = WriteService.audit(user)
            if row is None:
                row = await ViewPreferenceDao.insert(db, user_id=user.user.user_id, view_key=view_key,
                    project_id=project_id, settings=settings, **audit)
            else:
                row.settings = settings; row.revision += 1
                row.update_by = audit['update_by']; row.update_time = audit['update_time']
            return await WriteService.finish(db, user, path, key, raw, cls.result(view_key, project_id, row),
                                             'view_preference', row.preference_id, 'PUT')
        except Exception:
            await db.rollback()
            raise

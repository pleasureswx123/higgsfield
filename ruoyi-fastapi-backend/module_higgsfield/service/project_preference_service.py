"""个人项目导航仅修改本人数据，不授予项目权限。"""
from common.vo import PageModel
from module_higgsfield.dao.project_preference_dao import PreferenceDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.project_preference_do import HfProjectCollection, HfUserProjectPreference
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class PreferenceService:
    @staticmethod
    def collection_result(row):
        return dict(id=str(row.collection_id), name=row.collection_name, description=row.description,
                    color=row.color, orderNum=row.order_num, revision=str(row.revision))

    @staticmethod
    def preference_result(project_id, row):
        return dict(projectId=str(project_id), isPinned=bool(row and row.is_pinned == 'Y'),
                    isHidden=bool(row and row.is_hidden == 'Y'),
                    collectionId=str(row.collection_id) if row and row.collection_id else None,
                    orderNum=row.order_num if row else 0, revision=str(row.revision) if row else '0')

    @classmethod
    async def list_collections(cls, db, user, query):
        rows, total = await PreferenceDao.collections(db, user.user.user_id, query)
        return PageModel(rows=[cls.collection_result(row) for row in rows], total=total,
                         pageNum=query.page_num, pageSize=query.page_size,
                         hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def get_preference(cls, db, user, project_id):
        await WorkspaceService.authorize(db, user, project_id, 'project:read')
        return cls.preference_result(project_id, await PreferenceDao.preference(db, user.user.user_id, project_id))

    @classmethod
    async def mutate_collection(cls, db, user, action, payload, key, identity=None):
        path = '/project-collections' + (f'/{identity}' if identity is not None else '')
        method = {'create': 'POST', 'update': 'PATCH', 'delete': 'DELETE'}[action]
        uid = user.user.user_id
        try:
            await WriteService.lock(db, user, path, key)
            await PreferenceDao.lock_user(db, uid)
            # 幂等结果属于当前用户；删除后重试仍应返回原结果。
            replay = await WriteService.replay(db, user, path, key, payload, method)
            if replay:
                await db.commit()
                return replay, True
            row = await PreferenceDao.collection(db, uid, identity, True) if identity else None
            if action != 'create':
                if row is None:
                    WorkspaceService.conflict('RESOURCE_NOT_FOUND', '集合不存在或无权访问')
                if str(row.revision) != payload['revision']:
                    WorkspaceService.conflict('REVISION_CONFLICT', '集合已更新，请刷新后重试')
            if 'name' in payload and await PreferenceDao.name_used(db, uid, payload['name'], identity or 0):
                WorkspaceService.conflict('COLLECTION_NAME_EXISTS', '已存在同名集合')
            audit = WriteService.audit(user)
            if action == 'create':
                row = await PreferenceDao.insert(db, HfProjectCollection, user_id=uid,
                    collection_name=payload['name'], order_num=payload.get('orderNum', 0), **audit)
            elif action == 'update':
                for source, target in {'name': 'collection_name', 'description': 'description',
                                       'color': 'color', 'orderNum': 'order_num'}.items():
                    if source in payload:
                        setattr(row, target, payload[source])
                row.revision += 1
                row.update_by = audit['update_by']; row.update_time = audit['update_time']
            else:
                await PreferenceDao.remove_collection(db, row, audit['update_by'], audit['update_time'])
            result = cls.collection_result(row) if action != 'delete' else {'id': str(identity)}
            return await WriteService.finish(db, user, path, key, payload, result, 'project_collection',
                                             row.collection_id, method)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def put_preference(cls, db, user, project_id, payload, key):
        path = f'/projects/{project_id}/preferences'
        uid = user.user.user_id
        try:
            await WriteService.lock(db, user, path, key)
            # 与成员撤权共用项目锁，但不要求项目可写；归档项目仍能设置个人偏好。
            await WorkspaceDao.lock_project(db, project_id)
            await WorkspaceService.authorize(db, user, project_id, 'project:read')
            await PreferenceDao.lock_user(db, uid)
            replay = await WriteService.replay(db, user, path, key, payload, 'PUT')
            if replay:
                await db.commit()
                return replay, True
            row = await PreferenceDao.preference(db, uid, project_id, True)
            if payload['revision'] != (str(row.revision) if row else '0'):
                WorkspaceService.conflict('REVISION_CONFLICT', '个人偏好已更新，请刷新后重试')
            collection_id = payload.get('collectionId')
            if collection_id is not None and not await PreferenceDao.collection(db, uid, int(collection_id), True):
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '集合不存在或不属于本人')
            audit = WriteService.audit(user)
            if row is None:
                row = await PreferenceDao.insert(db, HfUserProjectPreference, user_id=uid, project_id=project_id, **audit)
            else:
                row.revision += 1
                row.update_by = audit['update_by']; row.update_time = audit['update_time']
            for source, target in {'isPinned': 'is_pinned', 'isHidden': 'is_hidden',
                                   'collectionId': 'collection_id', 'orderNum': 'order_num'}.items():
                if source in payload:
                    value = payload[source]
                    if source in ('isPinned', 'isHidden'):
                        value = 'Y' if value else 'N'
                    elif source == 'collectionId' and value is not None:
                        value = int(value)
                    setattr(row, target, value)
            return await WriteService.finish(db, user, path, key, payload, cls.preference_result(project_id, row),
                                             'project_preference', row.preference_id, 'PUT')
        except Exception:
            await db.rollback()
            raise

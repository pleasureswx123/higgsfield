"""收藏不赋权，每次创建/读取重新核验来源，取消仅需验证本人关系。"""
from common.vo import PageModel
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.favorite_dao import FavoriteDao as Dao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class FavoriteService:
    @staticmethod
    def target(row):
        for kind in Dao.targets:
            value = getattr(row, kind + '_id')
            if value is not None:
                return kind, int(value)
        raise ValueError('收藏关系缺少目标')

    @staticmethod
    async def source(db, user, kind, identity):
        if kind == 'element':
            element, project, _ = await ElementService.authorized(db, user, identity, 'element:read')
            return {'name': element.element_name, 'projectId': str(project.project_id),
                    'category': element.category, 'revision': str(element.revision)}
        if kind == 'asset':
            asset = await AssetService.get(db, user, identity)
            project_id = await AssetDao.project_id(db, identity)
            return {'name': asset['name'], 'projectId': str(project_id),
                    'mediaType': asset['mediaType'], 'revision': asset['revision']}
        output, _ = await OutputReadService.authorized(db, user, identity)
        return {'name': f'作品 #{output.ordinal + 1}', 'jobId': str(output.job_id),
                'mediaType': output.kind, 'revision': str(output.revision)}

    @classmethod
    async def create(cls, db, user, payload, key=None):
        path, data = '/favorites', payload.model_dump(by_alias=True, exclude_none=True)
        kind, identity = cls.target(payload.target)
        try:
            await WriteService.lock(db, user, path, key)
            await cls.source(db, user, kind, identity)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            row = await Dao.save(db, user.user.user_id, kind, identity, audit)
            result = {'id': str(row.favorite_id), 'target': {kind + 'Id': str(identity)}}
            await AssetDao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user',
                object_type='favorite', object_id=str(row.favorite_id), action='create',
                request_id=WriteService.digest({'path': path, 'key': key, 'target': data}),
                before_after={'after': result}, **audit)
            return await WriteService.finish(db, user, path, key, data, result, 'favorite', row.favorite_id)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def cancel(cls, db, user, identity, key=None):
        path = f'/favorites/{identity}'
        try:
            await WriteService.lock(db, user, path, key)
            row = await Dao.owned(db, user.user.user_id, identity)
            if row is None:
                WorkspaceService.conflict('FAVORITE_NOT_FOUND', '收藏不存在或不属于当前用户')
            replay = await WriteService.replay(db, user, path, key, {}, 'DELETE')
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            await Dao.cancel(db, user.user.user_id, identity, audit)
            await AssetDao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user',
                object_type='favorite', object_id=str(identity), action='cancel',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'after': {'cancelled': True}}, **audit)
            return await WriteService.finish(db, user, path, key, {}, {'id': str(identity), 'cancelled': True},
                                             'favorite', identity, method='DELETE')
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def listing(cls, db, user, query):
        rows, total = await Dao.page(db, user.user.user_id, query)
        result = []
        for row in rows:
            kind, identity = cls.target(row)
            item = {'id': str(row.favorite_id), 'target': {kind + 'Id': str(identity)},
                    'kind': kind, 'createTime': row.create_time, 'available': False}
            try:
                source = await cls.source(db, user, kind, identity)
            except PermissionException:
                pass
            except ServiceWarning as error:
                if not isinstance(error.data, dict) or error.data.get('errorCode') != 'RESOURCE_NOT_FOUND':
                    raise
            else:
                item.update(available=True, source=source)
            result.append(item)
        return PageModel(rows=result, total=total, pageNum=query.page_num, pageSize=query.page_size,
                         hasNext=query.page_num * query.page_size < total)

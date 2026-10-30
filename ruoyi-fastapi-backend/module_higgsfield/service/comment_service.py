"""评论目标每次重新授权，版本固定，正文、标注及审计原子提交。"""
from common.vo import PageModel
from types import SimpleNamespace
from fastapi.encoders import jsonable_encoder
from exceptions.exception import PermissionException
from utils.time_util import TimezoneUtil
from module_higgsfield.dao.comment_dao import CommentDao as Dao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.comment_do import HfCommentThread, HfComment, HfAnnotation, HfCommentReaction
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class CommentService:
    fail = WorkspaceService.conflict

    @classmethod
    async def authorize_target(cls, db, user, target, permission, write=False):
        if target.asset_version_id:
            version = await AssetDao.version(db, int(target.asset_version_id))
            asset = await AssetDao.asset(db, version.asset_id) if version else None
            project_id = await AssetDao.project_id(db, asset.asset_id) if asset else None
            if asset is None or project_id is None or asset.del_flag != '0':
                cls.fail('RESOURCE_NOT_FOUND', '评论目标不存在或无权访问')
            owner_id, kind, file_id = asset.create_user_id, asset.media_type, version.file_id
        else:
            output, _ = await OutputReadService.authorized(db, user, int(target.output_id))
            job = await GenerationReadDao.job(db, output.job_id)
            project_id, owner_id, kind = job.project_id, job.actor_id, output.kind
            file_id = output.file_id if output.archive_state == '2' else None
        await WorkspaceService.authorize(db, user, project_id, 'asset:read', owner_id=owner_id)
        await WorkspaceService.authorize(db, user, project_id, permission, write=write, owner_id=owner_id)
        file = await AssetDao.file(db, file_id) if file_id else None
        return project_id, kind, file

    @classmethod
    async def thread_authorized(cls, db, user, identity, permission, write=False, include_deleted=False):
        thread = await Dao.thread(db, identity, lock=write)
        if thread is None or (thread.del_flag != '0' and not include_deleted):
            cls.fail('RESOURCE_NOT_FOUND', '评论主题不存在或无权访问')
        context = await cls.authorize_target(db, user, thread, permission, write)
        return thread, context

    @staticmethod
    def thread_result(row):
        target = ({'assetVersionId': str(row.asset_version_id)} if row.asset_version_id
                  else {'outputId': str(row.output_id)})
        return {'id': str(row.thread_id), 'target': target, 'resolvedAt': row.resolved_time, 'revision': str(row.revision), 'createTime': row.create_time}

    @staticmethod
    async def audit(db, user, project_id, kind, identity, action, key, evidence):
        await AssetDao.add(db, HfAuditLog, project_id=project_id, actor_id=user.user.user_id,
            actor_kind='user', object_type=kind, object_id=str(identity), action=action,
            request_id=WriteService.digest({'kind': kind, 'id': str(identity), 'action': action, 'key': key}),
            before_after=jsonable_encoder(evidence), **WriteService.audit(user))

    @classmethod
    async def create_thread(cls, db, user, payload, key):
        path, data = '/comment-threads', payload.model_dump(by_alias=True, exclude_none=True)
        try:
            await WriteService.lock(db, user, path, key)
            project_id, _, _ = await cls.authorize_target(db, user, payload.target, 'comment:create', write=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            row = await AssetDao.add(db, HfCommentThread,
                asset_version_id=int(payload.target.asset_version_id) if payload.target.asset_version_id else None,
                output_id=int(payload.target.output_id) if payload.target.output_id else None,
                create_user_id=user.user.user_id, **WriteService.audit(user))
            result = cls.thread_result(row)
            await cls.audit(db, user, project_id, 'comment_thread', row.thread_id, 'create', key, {'target': result['target']})
            return await WriteService.finish(db, user, path, key, data, result, 'comment_thread', row.thread_id)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def threads(cls, db, user, query):
        await cls.authorize_target(db, user, query, 'comment:read')
        rows, total = await Dao.threads(db, query, query)
        return PageModel(rows=[cls.thread_result(row) for row in rows], total=total,
            pageNum=query.page_num, pageSize=query.page_size, hasNext=query.page_num * query.page_size < total)

    @classmethod
    def validate_media(cls, kind, file, payload):
        if payload.video_time is not None:
            if kind != 'video' or file is None or file.state != '1' or file.seconds is None or payload.video_time > file.seconds:
                cls.fail('COMMENT_TIME_INVALID', '视频时间点超出已归档目标时长或目标不可用')
        if payload.annotations:
            if kind != 'image' or file is None or file.state != '1':
                cls.fail('COMMENT_ANNOTATION_INVALID', '只有可用归档图片可以添加定位标注')
            if any(item.source_width != file.width or item.source_height != file.height for item in payload.annotations):
                cls.fail('COMMENT_DIMENSIONS_CHANGED', '标注原图尺寸必须与固定目标文件一致')

    @classmethod
    async def comment_result(cls, db, row):
        result = {'id': str(row.comment_id), 'threadId': str(row.thread_id),
            'parentId': str(row.parent_id) if row.parent_id else None, 'revision': str(row.revision),
            'createTime': row.create_time, 'deleted': row.del_flag == '2'}
        if row.del_flag == '2':
            return result | {'body': '', 'author': None, 'annotations': []}
        author = await WorkspaceDao.user(db, row.author_id)
        result.update(body=row.body, author={'id': str(row.author_id), 'displayName':
            (author['nick_name'] or author['user_name']) if author else '已删除用户'},
            videoTime=str(row.video_time) if row.video_time is not None else None,
            annotations=[{'shape': item.shape, 'geometry': item.geometry, 'color': item.color,
                'sourceWidth': item.source_width, 'sourceHeight': item.source_height}
                for item in await Dao.annotations(db, row.comment_id)])
        result['reactions'] = [{'emoji': item.emoji, 'userId': str(item.user_id)} for item in await Dao.reactions(db, row.comment_id)]
        return result

    @classmethod
    async def comments(cls, db, user, identity, query):
        _, (project_id, _, _) = await cls.thread_authorized(db, user, identity, 'comment:read')
        rows, total = await Dao.comments(db, identity, query)
        results = []
        for row in rows:
            result = await cls.comment_result(db, row)
            result['allowedActions'] = []
            if row.del_flag == '0':
                permissions = ['comment:moderate']
                if row.author_id == user.user.user_id:
                    permissions.insert(0, 'comment:edit:own')
                for permission in permissions:
                    try:
                        project, _, _ = await WorkspaceService.authorize(db, user, project_id, permission,
                            owner_id=row.author_id if permission == 'comment:edit:own' else None)
                    except PermissionException:
                        continue
                    if project.status == '0':
                        result['allowedActions'] = ['edit', 'delete']
                    break
            results.append(result)
        return PageModel(rows=results, total=total,
            pageNum=query.page_num, pageSize=query.page_size, hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def create_comment(cls, db, user, identity, payload, key):
        path = f'/comment-threads/{identity}/comments'
        data = payload.model_dump(mode='json', by_alias=True, exclude_none=True)
        try:
            await WriteService.lock(db, user, path, key)
            _, (project_id, kind, file) = await cls.thread_authorized(db, user, identity, 'comment:create', write=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                current = await Dao.comment(db, int(replay['data']['id']))
                if current is None or current.del_flag != '0':
                    cls.fail('COMMENT_REMOVED', '原评论已删除，不能重放正文')
                await db.commit()
                return replay, True
            parent_id = int(payload.parent_id) if payload.parent_id else None
            if parent_id:
                parent = await Dao.comment(db, parent_id)
                if parent is None or parent.thread_id != identity or parent.del_flag != '0':
                    cls.fail('COMMENT_PARENT_INVALID', '只能回复同主题内仍存在的评论')
            cls.validate_media(kind, file, payload)
            audit = WriteService.audit(user)
            row = await AssetDao.add(db, HfComment, thread_id=identity, parent_id=parent_id,
                author_id=user.user.user_id, body=payload.body, video_time=payload.video_time, **audit)
            for annotation in payload.annotations:
                await AssetDao.add(db, HfAnnotation, comment_id=row.comment_id, **annotation.model_dump(), **audit)
            await cls.audit(db, user, project_id, 'comment', row.comment_id, 'create', key,
                {'after': {'threadId': str(identity), 'parentId': payload.parent_id, 'annotationCount': len(payload.annotations)}})
            return await WriteService.finish(db, user, path, key, data,
                await cls.comment_result(db, row), 'comment', row.comment_id)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def mutate(cls, db, user, identity, payload, key, delete=False):
        path, method = f'/comments/{identity}', 'DELETE' if delete else 'PATCH'
        data = payload.model_dump(mode='json', by_alias=True, exclude_unset=True)
        try:
            await WriteService.lock(db, user, path, key)
            initial = await Dao.comment(db, identity)
            if initial is None:
                cls.fail('RESOURCE_NOT_FOUND', '评论不存在或无权访问')
            # 所有评论写入统一主题→项目→评论锁序，回复父项不能在校验后被删除。
            _, (project_id, kind, file) = await cls.thread_authorized(db, user, initial.thread_id, 'comment:read', write=True)
            row = await Dao.comment(db, identity, lock=True)
            if row.author_id == user.user.user_id:
                try:
                    await WorkspaceService.authorize(db, user, project_id, 'comment:edit:own', owner_id=row.author_id)
                except PermissionException:
                    await WorkspaceService.authorize(db, user, project_id, 'comment:moderate')
            else:
                await WorkspaceService.authorize(db, user, project_id, 'comment:moderate')
            if row.del_flag != '0' and not delete:
                cls.fail('COMMENT_REMOVED', '评论已删除，不能编辑或重放正文')
            replay = await WriteService.replay(db, user, path, key, data, method)
            if replay:
                await db.commit()
                return replay, True
            if row.del_flag != '0':
                cls.fail('COMMENT_REMOVED', '评论已删除')
            WorkspaceService.check_revision(row, payload.revision)
            before = await cls.comment_result(db, row)
            if delete:
                row.del_flag = '2'
            else:
                if 'annotations' in payload.model_fields_set:
                    cls.validate_media(kind, file, SimpleNamespace(video_time=None, annotations=payload.annotations))
                    await Dao.clear_annotations(db, identity)
                    for annotation in payload.annotations:
                        await AssetDao.add(db, HfAnnotation, comment_id=identity,
                            **annotation.model_dump(), **WriteService.audit(user))
                row.body = payload.body
            row.revision += 1
            row.update_by, row.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await AssetDao.flush(db)
            after = await cls.comment_result(db, row)
            await cls.audit(db, user, project_id, 'comment', identity, 'delete' if delete else 'edit', key,
                {'before': before, 'after': after, 'moderated': row.author_id != user.user.user_id})
            return await WriteService.finish(db, user, path, key, data, after, 'comment', identity, method=method)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def collaborate(cls, db, user, identity, payload, key, reaction=False):
        path = f'/comments/{identity}/reaction' if reaction else f'/comment-threads/{identity}'
        data = payload.model_dump(mode='json', by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            initial = await Dao.comment(db, identity) if reaction else None
            if reaction and (initial is None or initial.del_flag != '0'):
                cls.fail('COMMENT_REMOVED', '评论不存在或已删除')
            thread, (project_id, _, _) = await cls.thread_authorized(db, user, initial.thread_id if reaction else identity, 'comment:create' if reaction else 'comment:read', write=True, include_deleted=not reaction and payload.action == 'delete')
            if not reaction:
                permission = 'comment:edit:own' if thread.create_user_id == user.user.user_id else 'comment:moderate'
                try:
                    await WorkspaceService.authorize(db, user, project_id, permission, owner_id=thread.create_user_id)
                except PermissionException:
                    await WorkspaceService.authorize(db, user, project_id, 'comment:moderate')
            replay = await WriteService.replay(db, user, path, key, data, 'PATCH')
            if replay:
                await db.commit()
                return replay, True
            if thread.del_flag != '0':
                cls.fail('COMMENT_REMOVED', '讨论已删除')
            if reaction:
                comment = await Dao.comment(db, identity, lock=True)
                if comment.del_flag != '0':
                    cls.fail('COMMENT_REMOVED', '评论已删除')
                item = await Dao.reaction(db, identity, user.user.user_id, payload.emoji)
                if item is None:
                    item = await AssetDao.add(db, HfCommentReaction, comment_id=identity, user_id=user.user.user_id, emoji=payload.emoji, **WriteService.audit(user))
                item.del_flag = '0' if payload.active else '2'
                item.update_by, item.update_time = user.user.user_name, TimezoneUtil.utc_now()
                await AssetDao.flush(db)
                result = await cls.comment_result(db, comment)
            else:
                WorkspaceService.check_revision(thread, payload.revision)
                if payload.action == 'delete':
                    thread.del_flag = '2'
                else:
                    thread.resolved_time = TimezoneUtil.utc_now() if payload.action == 'resolve' else None
                thread.revision += 1
                thread.update_by, thread.update_time = user.user.user_name, TimezoneUtil.utc_now()
                await AssetDao.flush(db)
                result = cls.thread_result(thread)
            await cls.audit(db, user, project_id, 'comment' if reaction else 'comment_thread', identity, 'reaction' if reaction else payload.action, key, data)
            return await WriteService.finish(db, user, path, key, data, result, 'comment' if reaction else 'comment_thread', identity, method='PATCH')
        except Exception:
            await db.rollback()
            raise

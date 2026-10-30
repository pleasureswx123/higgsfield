from module_higgsfield.service.stored_media_service import StoredMediaService
from common.vo import PageModel
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.comment_dao import CommentDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry, HfUploadBinding
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.vo.asset_formats import asset_media_type
from starlette.concurrency import run_in_threadpool
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.docx_content_service import DocxContentService
from module_higgsfield.service.pptx_content_service import PptxContentService


class AssetService:
    """素材身份、不可变版本和唯一上传绑定在同一事务提交。"""

    fail = WorkspaceService.conflict

    @classmethod
    async def document_text(cls, db, user, version_id, storage=None):
        """只返回正文字符串，不解析HTML，也不执行Office内容。"""
        version = await AssetDao.version(db, version_id)
        if version is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材版本不存在或无权访问')
        project_id = await AssetDao.project_id(db, version.asset_id)
        asset = await AssetDao.asset(db, version.asset_id)
        if project_id is None or asset is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材不存在或无权访问')
        await WorkspaceService.authorize(db, user, project_id, 'asset:read', owner_id=asset.create_user_id)
        file = await AssetDao.file(db, version.file_id)
        if asset.del_flag != '0' or file is None or file.state != '1':
            cls.fail('FILE_NOT_READY', '文件不可用或素材已删除')
        mime, key, size = file.mime_type, file.storage_key, file.byte_size
        if mime not in {DocxContentService.mime, PptxContentService.mime, 'text/plain', 'text/markdown', 'text/html'}:
            cls.fail('DOCUMENT_PREVIEW_UNSUPPORTED', '该格式不支持文本预览')
        limit = 64 * 1024 * 1024
        if size > limit:
            cls.fail('DOCUMENT_PREVIEW_TOO_LARGE', '文档过大，请下载后查看')
        await db.rollback()
        storage = storage or StorageService()

        def extract():
            with storage.open_key(key) as handle:
                body = handle.read(limit + 1)
            if len(body) != size or len(body) > limit:
                raise ValueError('文档大小异常')
            if mime == DocxContentService.mime:
                sections = ['\n'.join(DocxContentService.paragraphs(body, max_bytes=limit))]
            elif mime == PptxContentService.mime:
                sections = PptxContentService.slides(body, max_bytes=limit)
            else:
                sections = [body.decode('utf-8-sig')]
            if sum(map(len, sections)) > 2000000:
                raise ValueError('预览文本超限')
            return {'versionId': str(version_id), 'mimeType': mime, 'sections': sections}

        try:
            return await run_in_threadpool(extract)
        except (ValueError, OSError, LookupError, BadZipFile, ParseError):
            cls.fail('DOCUMENT_PREVIEW_UNAVAILABLE', '无法读取文档正文，请下载原文件查看')

    @classmethod
    async def library(cls, db, user, project_id, query):
        project, role, _ = await WorkspaceService.authorize(db, user, project_id, 'asset:read')
        scopes = await WorkspaceDao.permission_scopes(db, role, project_id)
        space = await FolderDao.space(db, project_id)
        if query.folder_id:
            await FolderService.check_target(db, space.space_id, int(query.folder_id), 'media')
        rows, total = await AssetDao.library(db, space.space_id, query, user.user.user_id)
        can_read_comments = 'comment:read' in scopes and (role == 'owner' or '*:*:*' in user.permissions or 'comment:read' in user.permissions)
        comment_counts = await CommentDao.asset_version_counts(db, [asset.current_version_id for asset, _ in rows]) if can_read_comments else {}
        items = []
        for asset, entry in rows:
            result = await cls.result(db, asset)
            result['commentCount'] = comment_counts.get(asset.current_version_id, 0) if can_read_comments else None
            result['allowedActions'] = sorted(
                code
                for code in ('asset:edit', 'asset:remove', 'content:review')
                if project.status == '0'
                and code in scopes
                and (scopes[code] == 'project' or asset.create_user_id == user.user.user_id)
                and (role == 'owner' or '*:*:*' in user.permissions or code in user.permissions)
            )
            items.append(
                {
                    'id': str(entry.entry_id),
                    'entryId': str(entry.entry_id),
                    'kind': 'asset',
                    'name': asset.asset_name,
                    'createTime': asset.create_time,
                    'revision': str(entry.revision),
                    'folderId': str(entry.folder_id) if entry.folder_id else None,
                    'asset': result,
                }
            )
        return PageModel(
            rows=items,
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def move(cls, db, user, project_id, payload, key, copy=False):
        data, path = payload.model_dump(by_alias=True), f"/projects/{project_id}/library/{'copy' if copy else 'move'}"
        try:
            await WriteService.lock(db, user, path, key)
            await WorkspaceService.authorize(db, user, project_id, 'folder:write', write=True)
            space = await FolderDao.space(db, project_id, lock=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            entry = await AssetDao.entry(db, space.space_id, int(payload.entry_id))
            if entry is None:
                cls.fail('RESOURCE_NOT_FOUND', '素材归属不存在或无权访问')
            asset = await AssetDao.asset(db, entry.asset_id)
            if asset is None or asset.del_flag != '0':
                cls.fail('RESOURCE_REMOVED', '已回收素材不能移动，请先恢复素材')
            WorkspaceService.check_revision(entry, payload.revision)
            folder_id = int(payload.folder_id) if payload.folder_id else None
            await FolderService.check_target(db, space.space_id, folder_id, 'media')
            if copy:
                from module_higgsfield.service.folder_content_service import FolderContentService
                entry = await FolderContentService.copy(
                    db, user, project_id, space.space_id, entry.folder_id, folder_id, entry_id=entry.entry_id
                )
            else:
                entry.folder_id, entry.revision = folder_id, entry.revision + 1
                entry.update_by, entry.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await AssetDao.flush(db)
            return await WriteService.finish(
                db,
                user,
                path,
                key,
                data,
                {'entryId': str(entry.entry_id), 'folderId': payload.folder_id, 'revision': str(entry.revision)},
                'folder_entry',
                entry.entry_id,
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def media(cls, db, user, version_id, range_header=None, download=False, head=False, storage=None, thumbnail=False):
        version = await AssetDao.version(db, version_id)
        if version is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材版本不存在或无权访问')
        asset_id, file_id = version.asset_id, version.file_id
        project_id = await AssetDao.project_id(db, asset_id)
        if project_id is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材版本不存在或无权访问')
        asset, file = await AssetDao.asset(db, asset_id), await AssetDao.file(db, file_id)
        await WorkspaceService.authorize(
            db, user, project_id, 'asset:download' if download else 'asset:read', owner_id=asset.create_user_id
        )
        if asset.del_flag != '0' or file is None or file.state != '1':
            cls.fail('FILE_NOT_READY', '文件不可用或素材已删除')
        if thumbnail:
            from module_higgsfield.service.thumbnail_read_service import ThumbnailReadService
            return await ThumbnailReadService.stream(db, file, range_header, head, storage)
        key, size, mime, name = file.storage_key, file.byte_size, file.mime_type, asset.asset_name
        async def record_download(byte_range):
            try:
                # 打开文件期间事务已释放，发送前重新校验撤权及回收状态。
                await WorkspaceDao.lock_project(db, project_id)
                current = await AssetDao.asset(db, asset_id)
                if current is None:
                    cls.fail('RESOURCE_NOT_FOUND', '素材不存在或无权访问')
                await WorkspaceService.authorize(db, user, project_id, 'asset:download', owner_id=current.create_user_id)
                current_file = await AssetDao.file(db, file_id)
                if current.del_flag != '0' or current_file is None or current_file.state != '1':
                    cls.fail('FILE_NOT_READY', '文件不可用或素材已删除')
                await AssetDao.add(db, HfAuditLog, actor_kind='user', actor_id=user.user.user_id,
                    project_id=project_id, object_type='asset', object_id=str(asset_id), action='download_authorized',
                    request_id=str(uuid4()), before_after={'authorized': {'versionId': str(version_id),
                        'byteStart': str(byte_range.start), 'byteLength': str(byte_range.length),
                        'transferComplete': False}}, **WriteService.audit(user))
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        result = await StoredMediaService.stream(db, key, size, mime, name, range_header, download, head, storage,
                                                on_ready=record_download if download and not head else None)
        if asset_media_type(mime) == 'document' and not download:
            stream, headers, _, status = result
            headers['Content-Security-Policy'] = "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'"
            if mime in ('text/html', 'text/markdown', 'text/plain'):
                mime = 'text/plain; charset=utf-8'
            elif mime != 'application/pdf':
                # Office原件不能由浏览器直接执行；正文使用单独文本预览接口。
                headers['Content-Disposition'] = 'attachment'
            return stream, headers, mime, status
        return result

    @staticmethod
    async def result(db, asset, version=None):
        version = version or await AssetDao.version(db, asset.current_version_id)
        file = await AssetDao.file(db, version.file_id)
        return {
            'id': str(asset.asset_id),
            'spaceId': str(asset.space_id),
            'name': asset.asset_name,
            'mediaType': asset.media_type,
            'workStatus': asset.work_status,
            'currentVersionId': str(version.version_id),
            'uploaded': await AssetDao.is_uploaded_version(db, version.version_id),
            'revision': str(asset.revision),
            'createUserId': str(asset.create_user_id),
            'createTime': asset.create_time,
            'file': {
                'id': str(file.file_id),
                'mimeType': file.mime_type,
                'byteSize': str(file.byte_size),
                'width': file.width,
                'height': file.height,
                'seconds': str(file.seconds) if file.seconds is not None else None,
                'state': 'ready' if file.state == '1' else 'unavailable',
            },
        }

    @classmethod
    async def get(cls, db, user, asset_id):
        project_id = await AssetDao.project_id(db, asset_id)
        if project_id is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材不存在或无权访问')
        asset = await AssetDao.asset(db, asset_id)
        await WorkspaceService.authorize(db, user, project_id, 'asset:read', owner_id=asset.create_user_id)
        if asset.del_flag != '0':
            cls.fail('RESOURCE_NOT_FOUND', '素材不存在或已删除')
        return await cls.result(db, asset)

    @classmethod
    async def get_version(cls, db, user, version_id):
        """固定版本预览复用素材对象授权，避免元素引用误开最新版本。"""
        version = await AssetDao.version(db, version_id)
        if version is None:
            cls.fail('RESOURCE_NOT_FOUND', '素材版本不存在或无权访问')
        await cls.get(db, user, version.asset_id)
        asset = await AssetDao.asset(db, version.asset_id)
        return await cls.result(db, asset, version)

    @classmethod
    async def bind(cls, db, user, payload, key, asset_id=None):
        data = payload.model_dump(by_alias=True)
        path = '/assets' if asset_id is None else f'/assets/{asset_id}/versions'
        try:
            await WriteService.lock(db, user, path, key)
            project_id = int(payload.project_id) if asset_id is None else await AssetDao.project_id(db, asset_id)
            if project_id is None:
                cls.fail('RESOURCE_NOT_FOUND', '素材不存在或无权访问')
            existing_asset = await AssetDao.asset(db, asset_id) if asset_id else None
            await WorkspaceService.authorize(
                db,
                user,
                project_id,
                'asset:create' if asset_id is None else 'asset:edit',
                write=True,
                owner_id=existing_asset.create_user_id if existing_asset else None,
            )
            space = await FolderDao.space(db, project_id, lock=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            upload = await AssetDao.upload(db, int(payload.upload_id))
            if upload is None or upload.project_id != project_id or upload.owner_id != user.user.user_id:
                cls.fail('RESOURCE_NOT_FOUND', '上传不存在或不属于当前项目和用户')
            session = await UploadService.authorize(db, user, int(payload.upload_id), write=True)
            if session.project_id != project_id or session.state != '3':
                cls.fail('UPLOAD_NOT_READY', '上传尚未验证完成或不属于当前项目')
            if await AssetDao.binding(db, session.upload_id):
                cls.fail('UPLOAD_ALREADY_BOUND', '该上传已绑定素材，请使用原结果或重新上传')
            file = await AssetDao.file(db, session.completed_file_id)
            if (
                file is None
                or file.state != '1'
                or file.sha256 != session.verified_sha256
                or file.byte_size != session.byte_size
            ):
                cls.fail('FILE_NOT_READY', '上传文件尚未就绪或元数据不一致')
            media_type = asset_media_type(file.mime_type)
            if media_type is None:
                cls.fail('ASSET_FORMAT_UNSUPPORTED', '该上传格式不能绑定为素材')
            audit = WriteService.audit(user)
            if asset_id is None:
                parent = int(payload.folder_id) if payload.folder_id else None
                await FolderService.check_target(db, space.space_id, parent, 'media')
                asset = await AssetDao.add(
                    db,
                    HfAsset,
                    space_id=space.space_id,
                    asset_name=payload.name,
                    media_type=media_type,
                    create_user_id=user.user.user_id,
                    revision=1,
                    del_flag='0',
                    **audit,
                )
                version_no = 1
            else:
                asset = await AssetDao.asset(db, asset_id)
                if asset.del_flag != '0':
                    cls.fail('RESOURCE_NOT_FOUND', '素材已删除')
                WorkspaceService.check_revision(asset, payload.revision)
                if asset.media_type != media_type:
                    cls.fail('MEDIA_TYPE_MISMATCH', '新版本必须保持素材媒体类别')
                version_no = (await AssetDao.version(db, asset.current_version_id)).version_no + 1
                asset.revision += 1
                asset.update_by, asset.update_time = user.user.user_name, TimezoneUtil.utc_now()
            version = await AssetDao.add(
                db,
                HfAssetVersion,
                asset_id=asset.asset_id,
                version_no=version_no,
                file_id=file.file_id,
                create_user_id=user.user.user_id,
                media_metadata={
                    'mimeType': file.mime_type,
                    'width': file.width,
                    'height': file.height,
                    'seconds': str(file.seconds) if file.seconds is not None else None,
                },
                **audit,
            )
            asset.current_version_id = version.version_id
            await AssetDao.add(
                db,
                HfUploadBinding,
                session_id=session.upload_id,
                asset_version_id=version.version_id,
                bound_by=user.user.user_id,
                **audit,
            )
            if asset_id is None:
                await AssetDao.add(
                    db,
                    HfFolderEntry,
                    space_id=space.space_id,
                    folder_id=parent,
                    asset_id=asset.asset_id,
                    revision=1,
                    order_num=0,
                    **audit,
                )
            await AssetDao.flush(db)
            result = (
                await cls.result(db, asset)
                if asset_id is None
                else {
                    'id': str(version.version_id),
                    'assetId': str(asset.asset_id),
                    'versionNo': version.version_no,
                    'fileId': str(file.file_id),
                    'createTime': version.create_time,
                    'revision': str(asset.revision),
                }
            )
            return await WriteService.finish(db, user, path, key, data, result, 'asset', asset.asset_id)
        except Exception:
            await db.rollback()
            raise

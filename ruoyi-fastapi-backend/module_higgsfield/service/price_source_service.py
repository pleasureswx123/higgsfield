"""来源登记保留不可变原文，不自动抓取 URL 或发布价格。"""

from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfUploadBinding
from module_higgsfield.service.document_upload_service import DocumentUploadService
from module_higgsfield.service.stored_media_service import StoredMediaService
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


class PriceSourceService:
    @staticmethod
    def result(row):
        return {
            'id': str(row.source_id),
            'sourceType': row.source_type,
            'sourceUrl': row.source_url,
            'excerpt': row.excerpt,
            'observedAt': row.observed_time.isoformat(),
        }

    @classmethod
    async def get(cls, db, user, source_id):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        row = await PriceSourceDao.get(db, source_id)
        if row is None:
            WorkspaceService.conflict('PRICE_SOURCE_NOT_FOUND', '价格来源不存在')
        result = cls.result(row)
        result['attachment'] = await cls.attachment(db, row)
        return result

    @staticmethod
    async def attachment(db, row):
        if row.file_id is None:
            return None
        upload = await PriceSourceDao.upload(db, row.source_id)
        file = await AssetDao.file(db, row.file_id)
        if (upload is None or upload.purpose != 'price_source' or upload.project_id is not None
                or upload.completed_file_id != row.file_id or file is None or file.state != '1'
                or upload.verified_sha256 != file.sha256 or upload.byte_size != file.byte_size):
            WorkspaceService.conflict('FILE_NOT_READY', '价格证据附件不可用或关联不一致')
        return {'fileName': upload.file_name, 'mimeType': file.mime_type,
            'byteSize': str(file.byte_size), 'sha256': file.sha256,
            'downloadUrl': f'/api/admin/v1/price-sources/{row.source_id}/attachment/download'}

    @classmethod
    async def download(cls, db, user, source_id, range_header=None, head=False, storage=None):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        row = await PriceSourceDao.get(db, source_id)
        if row is None:
            WorkspaceService.conflict('PRICE_SOURCE_NOT_FOUND', '价格来源不存在')
        metadata = await cls.attachment(db, row)
        if metadata is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '价格来源没有附件')
        file = await AssetDao.file(db, row.file_id)
        return await StoredMediaService.stream(db, file.storage_key, file.byte_size, file.mime_type,
            metadata['fileName'], range_header, True, head, storage)

    @classmethod
    async def create(cls, db, user, payload, key):
        path, prefix = '/price-sources', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:write')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            upload, file = None, None
            if payload.upload_id is not None:
                upload = await DocumentUploadService.authorize(db, user, int(payload.upload_id), write=True)
                if upload.purpose != 'price_source':
                    WorkspaceService.conflict('UPLOAD_PURPOSE_MISMATCH', '价格证据只能使用价格来源上传会话')
                if upload.state != '3':
                    WorkspaceService.conflict('UPLOAD_NOT_READY', '证据上传尚未完成校验')
                if await AssetDao.binding(db, upload.upload_id):
                    WorkspaceService.conflict('UPLOAD_ALREADY_BOUND', '该上传已绑定正式证据，请使用原结果')
                file = await AssetDao.file(db, upload.completed_file_id)
                if (file is None or file.state != '1' or file.sha256 != upload.verified_sha256
                        or file.byte_size != upload.byte_size or file.mime_type != upload.declared_mime_type):
                    WorkspaceService.conflict('FILE_NOT_READY', '上传文件尚未就绪或元数据不一致')
            if payload.observed_at > TimezoneUtil.utc_now():
                WorkspaceService.conflict('PRICE_SOURCE_FUTURE_TIME', '来源获取时间不能晚于当前时间')
            audit = WriteService.audit(user)
            row = await PriceSourceDao.add(
                db,
                dict(
                    source_type=payload.source_type,
                    source_url=payload.source_url,
                    excerpt=payload.excerpt,
                    observed_time=payload.observed_at,
                    create_user_id=user.user.user_id,
                    file_id=file.file_id if file else None,
                    **audit,
                ),
            )
            if upload is not None:
                await AssetDao.add(db, HfUploadBinding, session_id=upload.upload_id,
                    price_source_id=row.source_id, bound_by=user.user.user_id, **audit)
            result = cls.result(row)
            result['attachment'] = await cls.attachment(db, row)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    object_type='price_source',
                    object_id=str(row.source_id),
                    action='create',
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'after': result},
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, result, 'price_source', row.source_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

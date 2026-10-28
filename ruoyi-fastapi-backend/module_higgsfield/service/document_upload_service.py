"""管理文档沿用分片协议，所有阶段校验所有者和用途权限。"""
from datetime import timedelta
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfUploadSession
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.document_storage_service import DocumentStorageService
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


class DocumentUploadService(UploadService):
    storage_class = DocumentStorageService
    api_prefix = '/api/admin/v1'
    upload_path = '/document-uploads'
    permissions = {'price_source': 'billing:price:write', 'reconciliation': 'billing:reconcile'}

    @classmethod
    async def authorize(cls, db, user, upload_id, write=False, allow_expired=False):
        session = await AssetDao.upload(db, upload_id, lock=write)
        if (session is None or session.owner_id != user.user.user_id
                or session.purpose not in cls.permissions or session.project_id is not None):
            cls.fail('RESOURCE_NOT_FOUND', '管理上传会话不存在或无权访问')
        await AdminScopeService.global_access(db, user, cls.permissions[session.purpose])
        if not allow_expired and not await AssetDao.binding(db, upload_id) and session.expires_time <= TimezoneUtil.utc_now():
            raise HTTPException(status_code=410, detail='UPLOAD_EXPIRED')
        return session

    @staticmethod
    async def result(db, session):
        result = await UploadService.result(db, session)
        result['projectId'] = None
        result['purpose'] = session.purpose
        return result

    @classmethod
    async def create(cls, db, user, payload, key, storage=None):
        storage = storage or cls.storage_class()
        data, path = payload.model_dump(by_alias=True), cls.upload_path
        try:
            await AdminScopeService.global_access(db, user, cls.permissions[payload.purpose])
            await db.rollback()
            if int(payload.byte_size) > storage.policy.max_bytes:
                cls.fail('UPLOAD_TOO_LARGE', '文件超过管理员配置的上传大小限制')
            await run_in_threadpool(storage.verify_root)
            await WriteService.lock(db, user, path, key, api_prefix=cls.api_prefix)
            await AdminScopeService.global_access(db, user, cls.permissions[payload.purpose])
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=cls.api_prefix)
            if replay:
                await cls.authorize(db, user, int(replay['data']['id']))
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            size, part_size = int(payload.byte_size), storage.policy.part_size
            session = await AssetDao.add(db, HfUploadSession, owner_id=user.user.user_id,
                project_id=None, purpose=payload.purpose, file_name=payload.file_name,
                declared_mime_type=payload.mime_type, byte_size=size, part_size=part_size,
                part_count=(size + part_size - 1) // part_size, expected_sha256=payload.sha256,
                state='0', expires_time=audit['create_time'] + timedelta(days=1), validation_errors=[],
                schema_version=1, revision=1, **audit)
            return await WriteService.finish(db, user, path, key, data, await cls.result(db, session),
                'upload', session.upload_id, api_prefix=cls.api_prefix)
        except Exception:
            await db.rollback()
            raise

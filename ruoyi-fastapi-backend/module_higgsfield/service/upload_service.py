import hashlib
import re
from datetime import timedelta

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from exceptions.exception import ServiceWarning

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfStoredFile, HfUploadPart, HfUploadSession
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.project_upload_storage_service import ProjectUploadStorageService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil

UPLOAD_STATES = dict(zip('0123456', ('created', 'uploading', 'verifying', 'ready', 'failed', 'cancelled', 'expired')))


class UploadService:
    """上传私有性优先于项目治理权限；文件操作前后分别鉴权。"""

    fail = WorkspaceService.conflict
    storage_class = ProjectUploadStorageService
    api_prefix = '/api/v1'
    upload_path = '/uploads'

    @classmethod
    async def authorize(cls, db, user, upload_id, write=False, allow_expired=False):
        session = await AssetDao.upload(db, upload_id)
        if session is None or session.owner_id != user.user.user_id or session.purpose != 'asset':
            cls.fail('RESOURCE_NOT_FOUND', '上传会话不存在或无权访问')
        project_id = session.project_id
        await WorkspaceService.authorize(db, user, project_id, 'asset:upload', write=write)
        session = await AssetDao.upload(db, upload_id, lock=write)
        bound = await AssetDao.binding(db, upload_id)
        if not allow_expired and not bound and session.expires_time <= TimezoneUtil.utc_now():
            raise HTTPException(status_code=410, detail='UPLOAD_EXPIRED')
        return session

    @staticmethod
    async def result(db, session):
        parts = await AssetDao.parts(db, session.upload_id)
        return {
            'id': str(session.upload_id),
            'projectId': str(session.project_id),
            'state': UPLOAD_STATES[session.state],
            'byteSize': str(session.byte_size),
            'partSize': str(session.part_size),
            'partCount': session.part_count,
            'receivedParts': [part.part_no for part in parts],
            'expiresAt': session.expires_time,
            'validationErrors': session.validation_errors,
        }

    @classmethod
    async def create(cls, db, user, payload, key, storage=None):
        storage = storage or cls.storage_class()
        if int(payload.byte_size) > storage.policy.max_bytes:
            cls.fail('UPLOAD_TOO_LARGE', '文件超过管理员配置的上传大小限制')
        await run_in_threadpool(storage.verify_root)
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, '/uploads', key)
            await WorkspaceService.authorize(db, user, int(payload.project_id), 'asset:upload', write=True)
            replay = await WriteService.replay(db, user, '/uploads', key, data)
            if replay:
                # 重放仍验证原上传归属和当前访问权。
                await cls.authorize(db, user, int(replay['data']['id']))
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            size, part_size = int(payload.byte_size), storage.policy.part_size
            session = await AssetDao.add(
                db,
                HfUploadSession,
                owner_id=user.user.user_id,
                project_id=int(payload.project_id),
                purpose='asset',
                file_name=payload.file_name,
                declared_mime_type=payload.mime_type,
                byte_size=size,
                part_size=part_size,
                part_count=(size + part_size - 1) // part_size,
                expected_sha256=payload.sha256,
                state='0',
                expires_time=audit['create_time'] + timedelta(days=1),
                validation_errors=[],
                schema_version=1,
                revision=1,
                **audit,
            )
            return await WriteService.finish(
                db, user, '/uploads', key, data, await cls.result(db, session), 'upload', session.upload_id
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get(cls, db, user, upload_id):
        return await cls.result(db, await cls.authorize(db, user, upload_id))

    @classmethod
    def part_shape(cls, session, part_no, content_range):
        offset = (part_no - 1) * session.part_size
        size = min(session.part_size, session.byte_size - offset)
        expected = f'bytes {offset}-{offset + size - 1}/{session.byte_size}'
        if part_no < 1 or part_no > session.part_count or content_range != expected:
            cls.fail('UPLOAD_RANGE_INVALID', '分片编号或Content-Range与会话不一致')
        return offset, size

    @classmethod
    async def put_part(cls, db, user, upload_id, part_no, content_range, claimed_hash, stream, storage=None):
        if not re.fullmatch(r'[a-f0-9]{64}', claimed_hash):
            cls.fail('UPLOAD_CHECKSUM_INVALID', '分片摘要格式不正确')
        storage = storage or cls.storage_class()
        try:
            session = await cls.authorize(db, user, upload_id, write=True)
            if session.state not in ('0', '1'):
                cls.fail('UPLOAD_STATE_CONFLICT', '当前会话不能再接收分片')
            offset, expected_size = cls.part_shape(session, part_no, content_range)
            await db.rollback()
            # 最多保留一片；接收网络流和写NAS时不占用数据库事务。
            body = bytearray()
            async for chunk in stream:
                if len(body) + len(chunk) > expected_size:
                    cls.fail('UPLOAD_RANGE_INVALID', '实际分片超过声明大小')
                body.extend(chunk)
            digest = hashlib.sha256(body).hexdigest()
            if len(body) != expected_size or digest != claimed_hash:
                cls.fail('UPLOAD_CHECKSUM_MISMATCH', '实际分片大小或摘要与声明不符')
            session = await cls.authorize(db, user, upload_id, write=True)
            if session.state not in ('0', '1'):
                cls.fail('UPLOAD_STATE_CONFLICT', '上传已取消或开始校验')
            saved = next((part for part in await AssetDao.parts(db, upload_id) if part.part_no == part_no), None)
            if saved:
                if saved.sha256 != digest or saved.byte_size != expected_size:
                    cls.fail('UPLOAD_PART_CONFLICT', '该分片编号已经保存了不同内容')
                await db.commit()
                return {'partNo': part_no, 'byteSize': str(expected_size), 'sha256': digest}
            await db.rollback()
            storage_key, _ = await run_in_threadpool(storage.put_part, body)
            session = await cls.authorize(db, user, upload_id, write=True)
            if session.state not in ('0', '1'):
                cls.fail('UPLOAD_STATE_CONFLICT', '上传已取消或开始校验')
            existing = next((part for part in await AssetDao.parts(db, upload_id) if part.part_no == part_no), None)
            if existing:
                if existing.sha256 != digest or existing.byte_size != expected_size:
                    cls.fail('UPLOAD_PART_CONFLICT', '该分片编号已经保存了不同内容')
            else:
                await AssetDao.add(
                    db,
                    HfUploadPart,
                    session_id=upload_id,
                    part_no=part_no,
                    byte_offset=offset,
                    byte_size=expected_size,
                    sha256=digest,
                    storage_key=storage_key,
                    **WriteService.audit(user),
                )
                session.state, session.revision = '1', session.revision + 1
                session.update_by, session.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.commit()
            return {'partNo': part_no, 'byteSize': str(expected_size), 'sha256': digest}
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def complete(cls, db, user, upload_id, payload, key, storage=None):
        storage = storage or cls.storage_class()
        data, path = payload.model_dump(by_alias=True), f'{cls.upload_path}/{upload_id}/complete'
        try:
            await WriteService.lock(db, user, path, key, api_prefix=cls.api_prefix)
            session = await cls.authorize(db, user, upload_id, write=True)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=cls.api_prefix)
            if replay:
                await db.commit()
                return replay, True
            if session.expected_sha256 and session.expected_sha256 != payload.sha256:
                cls.fail('UPLOAD_CHECKSUM_CONFLICT', '首次完成请求已固定文件摘要，不能更换')
            if session.state == '3':
                return await WriteService.finish(
                    db, user, path, key, data, await cls.result(db, session), 'upload', upload_id, api_prefix=cls.api_prefix
                )
            if session.state not in ('0', '1', '2'):
                cls.fail('UPLOAD_STATE_CONFLICT', '上传已失败、取消或过期')
            parts = await AssetDao.parts(db, upload_id)
            if [part.part_no for part in parts] != list(range(1, session.part_count + 1)):
                cls.fail('UPLOAD_INCOMPLETE', '尚有分片未完成上传')
            snapshot = [
                {'storage_key': part.storage_key, 'sha256': part.sha256, 'byte_size': part.byte_size} for part in parts
            ]
            expected_size, mime = session.byte_size, session.declared_mime_type
            session.expected_sha256, session.state = payload.sha256, '2'
            session.revision += 1
            session.update_by, session.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.commit()
            # 崩溃后重试继续同一摘要；并发完成最多一条文件记录，孤立对象留待审计清理。
            try:
                verified = await run_in_threadpool(storage.assemble, snapshot, expected_size, payload.sha256, mime)
            except ServiceWarning as failure:
                code = failure.data.get('errorCode') if isinstance(failure.data, dict) else None
                if code in ('MEDIA_INVALID', 'MEDIA_TYPE_MISMATCH', 'UPLOAD_CHECKSUM_MISMATCH'):
                    session = await cls.authorize(db, user, upload_id, write=True)
                    if session.state == '2' and session.expected_sha256 == payload.sha256:
                        session.state, session.revision = '4', session.revision + 1
                        session.validation_errors = [{'field': 'file', 'code': code, 'message': failure.message}]
                        session.update_by, session.update_time = user.user.user_name, TimezoneUtil.utc_now()
                        await db.commit()
                raise
            session = await cls.authorize(db, user, upload_id, write=True)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=cls.api_prefix)
            if replay:
                await db.commit()
                return replay, True
            if session.state == '2' and session.expected_sha256 == payload.sha256:
                file = await AssetDao.add(db, HfStoredFile, **verified, state='1', **WriteService.audit(user))
                session.completed_file_id, session.verified_sha256, session.state = file.file_id, payload.sha256, '3'
                session.revision += 1
                session.update_by, session.update_time = user.user.user_name, TimezoneUtil.utc_now()
            elif session.state != '3':
                cls.fail('UPLOAD_STATE_CONFLICT', '完成期间上传状态发生变化')
            await AssetDao.flush(db)
            return await WriteService.finish(
                db, user, path, key, data, await cls.result(db, session), 'upload', upload_id, api_prefix=cls.api_prefix
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def cancel(cls, db, user, upload_id):
        try:
            session = await cls.authorize(db, user, upload_id, write=True, allow_expired=True)
            if await AssetDao.binding(db, upload_id):
                cls.fail('UPLOAD_ALREADY_BOUND', '上传已经绑定正式素材，不能取消或删除文件')
            if session.state != '5':
                session.state, session.revision = '5', session.revision + 1
                session.update_by, session.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.commit()
        except Exception:
            await db.rollback()
            raise

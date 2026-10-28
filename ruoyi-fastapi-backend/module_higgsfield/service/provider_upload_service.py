"""上传意图、调用事实与加密地址短事务；未知上传不得自动重复。"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_upload_dao import ProviderUploadDao
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.generation_access_service import GenerationAccessService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_http_service import ProviderHttpResult
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.provider_upload_crypto_service import ProviderUploadCryptoService
from module_higgsfield.service.provider_upload_response_service import ProviderUploadResponseService
from module_higgsfield.service.write_service import WriteService

MAX_REQUIRED_SECONDS = 604800


@dataclass(frozen=True)
class UploadPreparation:
    upload_id: int
    status: Literal['upload', 'ready', 'busy', 'unknown']
    call_id: int | None = None
    url: SecretStr | None = None


class ProviderUploadService:
    @staticmethod
    async def ready_url(
        db: AsyncSession,
        lease: JobLease,
        upload_id: int,
        *,
        required_seconds: int,
        crypto: ProviderUploadCryptoService,
    ) -> SecretStr:
        job, now = await JobLeaseService.guard(db, lease)
        upload = await ProviderUploadDao.locked(db, upload_id)
        allowed = {item['assetVersionId'] for item in job.input_snapshot.get('compiled', {}).get('media', [])}
        if (
            upload is None
            or upload.state != '1'
            or str(upload.asset_version_id) not in allowed
            or upload.credential_version_id != job.credential_version_id
            or str(upload.account_id) != job.input_snapshot.get('route', {}).get('accountId')
            or upload.expires_time <= now + timedelta(seconds=required_seconds)
        ):
            WorkspaceService.conflict('PROVIDER_UPLOAD_UNRESOLVED', '上传结果不可用或有效期不足，不能提交生成')
        return SecretStr(crypto.decrypt(upload.url_ciphertext, upload.provider_upload_id, upload.credential_version_id))

    @staticmethod
    async def begin(
        db: AsyncSession,
        lease: JobLease,
        asset_version_id: int,
        *,
        required_seconds: int,
        crypto: ProviderUploadCryptoService | None = None,
    ) -> UploadPreparation:
        if type(required_seconds) is not int or not 1 <= required_seconds <= MAX_REQUIRED_SECONDS:
            raise ValueError('上传地址所需有效期无效')
        try:
            job, _ = await JobLeaseService.guard(db, lease)
            if job.orchestration_state != '1':
                WorkspaceService.conflict('UPLOAD_STAGE_INVALID', '只能在任务准备阶段上传引用媒体')
            await GenerationAccessService.require(db, job)
            media = next(
                (
                    item
                    for item in job.input_snapshot.get('compiled', {}).get('media', [])
                    if item.get('assetVersionId') == str(asset_version_id)
                ),
                None,
            )
            source = await AssetDao.version(db, asset_version_id)
            file = await AssetDao.file(db, source.file_id) if source else None
            if (
                media is None
                or file is None
                or file.state != '1'
                or media.get('fileId') != str(file.file_id)
                or media.get('sha256') != file.sha256
                or media.get('byteSize') != str(file.byte_size)
                or media.get('mimeType') != file.mime_type
                or media.get('mediaType') not in {'image', 'video'}
            ):
                WorkspaceService.conflict('UPLOAD_SOURCE_INVALID', '上传源不属于固定引用或文件身份已变化')
            job, now, account, version, config = await ProviderJobBindingService.require(db, lease, job)
            await ProviderUploadDao.lock_scope(db, asset_version_id, account.account_id, version.credential_version_id)
            job, now = await JobLeaseService.guard(db, lease)
            reusable = await ProviderUploadDao.reusable(
                db,
                asset_version_id,
                account.account_id,
                version.credential_version_id,
                now + timedelta(seconds=required_seconds),
            )
            if reusable:
                url = (crypto or ProviderUploadCryptoService()).decrypt(
                    reusable.url_ciphertext, reusable.provider_upload_id, reusable.credential_version_id
                )
                result = UploadPreparation(reusable.provider_upload_id, 'ready', url=SecretStr(url))
                await db.commit()
                return result
            pending = await ProviderUploadDao.unresolved(
                db, asset_version_id, account.account_id, version.credential_version_id
            )
            if pending:
                call = await ProviderCallDao.locked(db, pending.provider_call_id)
                if (
                    pending.state == '0'
                    and call
                    and call.state == '1'
                    and call.job_id == job.job_id
                    and call.request_metadata.get('fencingToken') != str(lease.fencing_token)
                ):
                    pending.state, call.state = '3', '3'
                    pending.update_by, pending.update_time = lease.worker, now
                    call.finished_time, call.update_time, call.update_by = now, now, lease.worker
                    call.response_metadata = {'recoveryReason': 'upload_lease_lost'}
                result = UploadPreparation(pending.provider_upload_id, 'unknown' if pending.state == '3' else 'busy')
                await db.commit()
                return result
            audit = {'create_time': now, 'update_time': now, 'create_by': lease.worker, 'update_by': lease.worker}
            metadata = {
                'assetVersionId': str(asset_version_id),
                'fileId': str(file.file_id),
                'sha256': file.sha256,
                'byteSize': str(file.byte_size),
                'mimeType': file.mime_type,
                'connectionVersionId': str(config.connection_version_id),
                'adapterVersion': config.adapter_version,
                'fencingToken': str(lease.fencing_token),
            }
            call = await ProviderCallDao.add(
                db,
                {
                    'job_id': job.job_id,
                    'account_id': account.account_id,
                    'credential_version_id': version.credential_version_id,
                    'operation': 'upload',
                    'request_hash': WriteService.digest(metadata),
                    'request_metadata': metadata,
                    'state': '1',
                    'acceptance': 'unknown',
                    'started_time': now,
                    **audit,
                },
            )
            upload = await ProviderUploadDao.add(
                db,
                {
                    'asset_version_id': asset_version_id,
                    'account_id': account.account_id,
                    'credential_version_id': version.credential_version_id,
                    'provider_call_id': call.call_id,
                    **audit,
                },
            )
            result = UploadPreparation(upload.provider_upload_id, 'upload', call_id=call.call_id)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def record(
        db: AsyncSession,
        lease: JobLease,
        upload_id: int,
        result: ProviderHttpResult,
        *,
        crypto: ProviderUploadCryptoService | None = None,
    ) -> None:
        try:
            job, now = await JobLeaseService.guard(db, lease)
            upload = await ProviderUploadDao.locked(db, upload_id)
            call = await ProviderCallDao.locked(db, upload.provider_call_id) if upload else None
            if (
                upload is None
                or call is None
                or upload.state != '0'
                or call.state != '1'
                or call.operation != 'upload'
                or call.job_id != job.job_id
                or job.orchestration_state != '1'
                or call.credential_version_id != job.credential_version_id
                or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
            ):
                WorkspaceService.conflict('UPLOAD_RESULT_STALE', '上传响应不属于当前任务租约')
            job, now = await JobLeaseService.guard(db, lease)
            parsed = None
            if result.transport == 'response' and type(result.http_status) is int:
                try:
                    parsed = ProviderUploadResponseService.parse(
                        result.http_status,
                        result.body,
                        received_at=now,
                        expected_size=int(call.request_metadata['byteSize']),
                        expected_mime=call.request_metadata['mimeType'],
                    )
                except ValueError:
                    pass
            call.state = '2' if result.transport == 'response' else '3'
            call.acceptance = 'not_applicable' if parsed else 'unknown'
            call.http_status, call.finished_time = result.http_status, now
            call.update_by, call.update_time = lease.worker, now
            upload.update_by, upload.update_time = lease.worker, now
            if parsed:
                upload.state = '1'
                upload.url_ciphertext = (crypto or ProviderUploadCryptoService()).encrypt(
                    parsed.source_url.get_secret_value(), upload.provider_upload_id, upload.credential_version_id
                )
                upload.expires_time = parsed.expires_at
                call.response_metadata = parsed.model_dump(mode='json', by_alias=True, exclude={'source_url'})
            else:
                upload.state = '3'
                call.response_metadata = {'issue': 'UPLOAD_RESULT_UNKNOWN'}
            await db.commit()
        except Exception:
            await db.rollback()
            raise

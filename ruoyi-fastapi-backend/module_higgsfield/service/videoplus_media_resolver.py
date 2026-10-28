"""将固定平台文件上传为短期外部地址，不把NAS路径发送给供应商。"""

import os

from pydantic import SecretStr

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.vo.provider_media_policy_vo import ProviderMediaPolicies
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.provider_upload_crypto_service import ProviderUploadCryptoService
from module_higgsfield.service.provider_upload_service import ProviderUploadService
from module_higgsfield.service.provider_upload_stream import ProviderUploadStream
from module_higgsfield.service.storage_io_service import open_source
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.write_service import WriteService


class VideoPlusMediaResolver:
    def __init__(
        self,
        *,
        credential_crypto: CredentialCryptoService,
        policies: ProviderMediaPolicies | None = None,
        storage: StorageService | None = None,
    ) -> None:
        self.credentials, self.policies, self.storage = credential_crypto, policies, storage
        self.crypto = ProviderUploadCryptoService(credential_crypto.keyring)

    def configured(self) -> ProviderMediaPolicies:
        if self.policies is not None:
            return self.policies
        try:
            return ProviderMediaPolicies.model_validate_json(os.environ['HF_PROVIDER_MEDIA_POLICY'])
        except (KeyError, ValueError):
            WorkspaceService.conflict('PROVIDER_MEDIA_POLICY_MISSING', '未配置已核实的供应商媒体直传策略')

    async def __call__(self, context: JobExecutionContext, compiled: dict) -> dict[int, SecretStr]:
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if WriteService.digest(compiled) != WriteService.digest(job.input_snapshot.get('compiled')):
                WorkspaceService.conflict('UPLOAD_SOURCE_INVALID', '媒体清单与固定任务快照不一致')
            policy = self.configured().model_versions.get(str(job.model_version_id))
            if policy is None:
                WorkspaceService.conflict('PROVIDER_MEDIA_POLICY_MISSING', '该模型版本未核实直传引用策略')
        media = compiled['media']
        for item in media:
            limit = policy.mime_limits.get(item['mimeType'])
            if item['mediaRole'] not in policy.roles or limit is None or not 0 < int(item['byteSize']) <= limit:
                WorkspaceService.conflict('PROVIDER_MEDIA_UNSUPPORTED', '引用角色、类型或大小不符合已核实的直传策略')
        storage = self.storage or StorageService()
        identities = {}
        for item in media:
            async with context.sessions() as db:
                prepared = await ProviderUploadService.begin(
                    db,
                    context.lease,
                    int(item['assetVersionId']),
                    required_seconds=policy.required_seconds,
                    crypto=self.crypto,
                )
            if prepared.status == 'upload':
                async with context.sessions() as db:
                    job, _ = await JobLeaseService.guard(db, context.lease)
                    _, _, _, version, config = await ProviderJobBindingService.require(db, context.lease, job)
                    file = await AssetDao.file(db, int(item['fileId']))
                    if file is None or file.state != '1':
                        WorkspaceService.conflict('UPLOAD_SOURCE_INVALID', '固定文件已不可读取')
                    key = file.storage_key
                    transport = ProviderHttpService.from_versions(config, version, crypto=self.credentials)
                async with open_source(storage, key) as handle:
                    upload = ProviderUploadStream(
                        handle,
                        file_name='reference-' + str(item['fileId']),
                        mime_type=item['mimeType'],
                        byte_size=int(item['byteSize']),
                        sha256=item['sha256'],
                        max_bytes=policy.mime_limits[item['mimeType']],
                    )
                    result = await transport.upload(upload)
                async with context.sessions() as db:
                    await ProviderUploadService.record(
                        db, context.lease, prepared.upload_id, result, crypto=self.crypto
                    )
            elif prepared.status != 'ready':
                WorkspaceService.conflict('PROVIDER_UPLOAD_UNRESOLVED', '上传尚未确认可用，不能提交生成')
            identities[item['ordinal']] = prepared.upload_id
        # 全部上传完成后重新检查有效期；不能为刷新刚返回的短期地址再次创建上传意图。
        urls = {}
        for ordinal, identity in identities.items():
            async with context.sessions() as db:
                urls[ordinal] = await ProviderUploadService.ready_url(
                    db, context.lease, identity, required_seconds=policy.required_seconds, crypto=self.crypto
                )
        return urls

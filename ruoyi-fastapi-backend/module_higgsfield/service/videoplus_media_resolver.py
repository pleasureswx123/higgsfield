"""将固定平台文件上传为短期外部地址，不把NAS路径发送给供应商。"""

import os

from pydantic import SecretStr

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.dao.provider_upload_dao import ProviderUploadDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.entity.vo.provider_media_policy_vo import DirectUploadPolicy
from module_higgsfield.service.videoplus_asset_response_service import VideoPlusAssetResponseService
from module_higgsfield.entity.vo.provider_media_policy_vo import ProviderMediaPolicies
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_exchange_service import ProviderExchangeService
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
            model = await ModelDao.version(db, job.model_version_id)
            alias = model.gateway_alias
            if self.policies is None and (alias.startswith(('mm-eva-sd-', 'mm-nova-sd-')) or alias == 'mm-h3'):
                policy = DirectUploadPolicy(roles=['first_frame', 'last_frame', 'reference_image', 'reference_person', 'reference_video'],
                    mimeLimits={**{mime: 20_000_000 for mime in ['image/jpeg', 'image/png', 'image/webp', 'image/gif']},
                                **{mime: 500_000_000 for mime in ['video/mp4', 'video/quicktime', 'video/webm']}},
                    requiredSeconds=3600, evidenceRef='供应商上传接口：图片20MB、视频500MB，URL有效期24小时')
            else:
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
                    ProviderExchangeService.bind(transport, context, prepared.call_id)
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
            if media[ordinal]['mediaRole'] == 'reference_person':
                # 先发起所有人物的注册，让供应商同时处理；不能等待第一张就绪才注册第二张。
                await self.person_reference(context, identity, urls[ordinal],
                    project='eva' if alias.startswith('mm-eva-') else 'nova', register_only=True)
        for ordinal, identity in identities.items():
            if media[ordinal]['mediaRole'] == 'reference_person':
                urls[ordinal] = await self.person_reference(context, identity, urls[ordinal],
                    project='eva' if alias.startswith('mm-eva-') else 'nova')
        return urls

    async def person_reference(self, context, upload_id, source, *, project, register_only=False):
        """复用同一上传、账号和区域的素材注册事实；结果不明时不重复注册。"""
        async with context.sessions() as db:
            job, now = await JobLeaseService.guard(db, context.lease)
            _, _, _, version, config = await ProviderJobBindingService.require(db, context.lease, job)
            transport = ProviderHttpService.from_versions(config, version, crypto=self.credentials)
            upload = await ProviderUploadDao.locked(db, upload_id)
            call = await ProviderCallDao.locked(db, upload.provider_call_id)
            registry = dict(call.response_metadata.get('assetRegistrations', {}))
            registration = registry.get(project)
            if registration is None:
                registration_call = await self.asset_call(db, job, now, upload, 'register', project, context.lease.worker)
                registry[project] = {'state': 'registering', 'callId': str(registration_call.call_id)}
                call.response_metadata = {**call.response_metadata, 'assetRegistrations': registry}
            await db.commit()
        if registration is None:
            ProviderExchangeService.bind(transport, context, registration_call.call_id)
            response = await transport.register_asset(source.get_secret_value(), project=project, asset_type='Image', name='人物参考图')
            await self.record_asset_call(context, registration_call.call_id, response)
            identity = VideoPlusAssetResponseService.registration(response.http_status or 0, response.body)
            async with context.sessions() as db:
                await JobLeaseService.guard(db, context.lease)
                upload = await ProviderUploadDao.locked(db, upload_id)
                call = await ProviderCallDao.locked(db, upload.provider_call_id)
                registry = dict(call.response_metadata.get('assetRegistrations', {}))
                registration = {'state': 'registered', 'id': identity, 'callId': str(registration_call.call_id)}
                registry[project] = registration
                call.response_metadata = {**call.response_metadata, 'assetRegistrations': registry}
                await db.commit()
        if not registration.get('id'):
            WorkspaceService.conflict('ASSET_REGISTRATION_UNKNOWN', '人物素材注册结果待核查，不会自动重复注册')
        if register_only:
            return
        async with context.sessions() as db:
            job, now = await JobLeaseService.guard(db, context.lease)
            upload = await ProviderUploadDao.locked(db, upload_id)
            query_call = await self.asset_call(db, job, now, upload, 'asset_get', project, context.lease.worker)
            await db.commit()
        ProviderExchangeService.bind(transport, context, query_call.call_id)
        response = await transport.get_asset(registration['id'])
        await self.record_asset_call(context, query_call.call_id, response)
        state = VideoPlusAssetResponseService.status(response.http_status or 0, response.body, expected_id=registration['id'])
        if state != 'Active':
            WorkspaceService.conflict('ASSET_PROCESSING' if state == 'Processing' else 'ASSET_REGISTRATION_FAILED',
                '人物参考素材正在处理' if state == 'Processing' else '人物参考素材注册失败')
        return SecretStr(VideoPlusAssetResponseService.reference(response.http_status, response.body, expected_id=registration['id']))

    @staticmethod
    async def asset_call(db, job, now, upload, operation, project, worker):
        """上传可跨任务复用，但每次注册/查询的网络证据必须属于当前任务。"""
        metadata = {'providerUploadId': str(upload.provider_upload_id), 'project': project}
        return await ProviderCallDao.add(db, dict(job_id=job.job_id, account_id=upload.account_id,
            credential_version_id=job.credential_version_id, operation=operation,
            request_hash=WriteService.digest(metadata), request_metadata=metadata,
            state='1', acceptance='unknown', started_time=now,
            create_time=now, update_time=now, create_by=worker, update_by=worker))

    @staticmethod
    async def record_asset_call(context, call_id, response):
        async with context.sessions() as db:
            _, now = await JobLeaseService.guard(db, context.lease)
            call = await ProviderCallDao.locked(db, call_id)
            if call is None or call.job_id != context.lease.job_id:
                raise ValueError('素材调用不属于当前任务')
            received = response.transport == 'response'
            call.state = '2' if received else '3'
            call.acceptance = 'not_applicable' if received else 'unknown'
            call.http_status = response.http_status
            call.finished_time = call.update_time = now
            call.update_by = context.lease.worker
            call.response_metadata = {'transport': response.transport}
            await db.commit()

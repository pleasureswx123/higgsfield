"""视频提交处理器；先固定请求并提交发送意图，网络结果不明时不重发。"""

from collections.abc import Awaitable, Callable

from pydantic import SecretStr

from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.provider_response_service import ProviderResponseService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.videoplus_request_service import VideoPlusRequestService
from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService
from module_higgsfield.service.write_service import WriteService

MediaResolver = Callable[[JobExecutionContext, dict], Awaitable[dict[int, SecretStr]]]


class VideoPlusSubmitHandler:
    def __init__(
        self, *, credential_crypto: CredentialCryptoService | None = None, media_resolver: MediaResolver | None = None,
        evidence_storage: ProviderResponseStorageService | None = None,
    ) -> None:
        self.credential_crypto, self.media_resolver = credential_crypto, media_resolver
        self.evidence_storage = evidence_storage

    async def __call__(self, context: JobExecutionContext) -> None:
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            needs_prepare = job.orchestration_state == '0'
        if needs_prepare:
            await context.advance('prepare')
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if job.kind != 'video' or job.orchestration_state != '1':
                WorkspaceService.conflict('PROVIDER_SUBMIT_UNAVAILABLE', '任务不满足视频提交条件')
            job, _, _, version, config = await ProviderJobBindingService.require(db, context.lease, job)
            model_version = await ModelDao.version(db, job.model_version_id)
            model = await ModelDao.model(db, model_version.model_id) if model_version else None
            if (
                config.adapter_version != 'videoplus-v1'
                or model is None
                or model.kind != 'video'
                or model.connection_id != config.connection_id
                or model_version.status != '2'
            ):
                WorkspaceService.conflict('PROVIDER_ADAPTER_UNSUPPORTED', '固定模型或连接不支持当前视频适配器')
            transport = ProviderHttpService.from_versions(config, version, crypto=self.credential_crypto)
            capabilities = ModelCapabilities.model_validate(model_version.capabilities)
            alias, snapshot = model_version.gateway_alias, job.input_snapshot
        urls = None
        if snapshot['compiled']['media'] and self.media_resolver:
            urls = await self.media_resolver(context, snapshot['compiled'])
        payload = VideoPlusRequestService.video(alias, capabilities, snapshot, urls)
        call_id = await context.begin_submission(WriteService.digest(payload))
        result = await transport.submit(payload)
        if result.transport == 'response':
            if result.body is not None and self.evidence_storage is not None:
                evidence = await self.evidence_storage.save(result.body, call_id, context.lease.job_id)
                async with context.sessions() as db:
                    await ProviderResponseService.register(
                        db, context.lease, call_id, evidence, http_status=result.http_status
                    )
            fact = VideoPlusResponseService.submission(result.http_status, result.body)
        else:
            fact = ProviderSubmissionResult(acceptance='unknown', transport=result.transport)
        await context.record_submission(call_id, fact)

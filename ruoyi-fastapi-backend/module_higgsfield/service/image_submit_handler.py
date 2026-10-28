"""同步图片工作器处理器；外部请求与落盘均在数据库事务外执行。"""

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.image_request_service import ImageRequestService
from module_higgsfield.service.image_response_service import ImageResponseService
from module_higgsfield.service.image_storage_service import ImageStorageService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_http_service import HARD_RESPONSE_BYTES, ProviderHttpService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.provider_response_service import ProviderResponseService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.write_service import WriteService


class ImageSubmitHandler:
    def __init__(
        self,
        storage: ImageStorageService,
        *,
        evidence_storage: ProviderResponseStorageService,
        max_decoded_bytes: int,
        credential_crypto=None,
        media_resolver=None,
    ):
        if type(max_decoded_bytes) is not int or not 0 < max_decoded_bytes:
            raise ValueError('图片响应解码上限必须为正整数')
        self.response_limit = 4 * ((max_decoded_bytes + 2) // 3) + 1_000_000
        if self.response_limit > HARD_RESPONSE_BYTES:
            raise ValueError('图片响应配置超过传输硬上限')
        self.storage, self.max_decoded_bytes = storage, max_decoded_bytes
        self.credentials, self.media_resolver = credential_crypto, media_resolver
        if evidence_storage.max_bytes < self.response_limit:
            raise ValueError('响应证据容量必须覆盖HTTP响应上限')
        self.evidence_storage = evidence_storage

    async def __call__(self, context: JobExecutionContext) -> None:
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            needs_prepare = job.orchestration_state == '0'
        if needs_prepare:
            await context.advance('prepare')
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if job.kind != 'image' or job.orchestration_state != '1':
                WorkspaceService.conflict('PROVIDER_SUBMIT_UNAVAILABLE', '任务不满足图片提交条件')
            job, _, _, version, config = await ProviderJobBindingService.require(db, context.lease, job)
            model_version = await ModelDao.version(db, job.model_version_id)
            model = await ModelDao.model(db, model_version.model_id) if model_version else None
            if (
                config.adapter_version != 'videoplus-v1'
                or model is None
                or model.kind != 'image'
                or model.connection_id != config.connection_id
                or model_version.status != '2'
            ):
                WorkspaceService.conflict('PROVIDER_ADAPTER_UNSUPPORTED', '固定模型或连接不支持当前图片适配器')
            transport = ProviderHttpService.from_versions(
                config,
                version,
                crypto=self.credentials,
                max_response_bytes=self.response_limit,
            )
            capabilities = ModelCapabilities.model_validate(model_version.capabilities)
            alias, snapshot = model_version.gateway_alias, job.input_snapshot
        urls = None
        if snapshot['compiled']['media'] and self.media_resolver:
            urls = await self.media_resolver(context, snapshot['compiled'])
        payload = ImageRequestService.compile(alias, capabilities, snapshot, urls)
        call_id = await context.begin_submission(WriteService.digest(payload))
        response = await transport.submit(payload)
        if response.transport != 'response':
            await context.record_submission(
                call_id, ProviderSubmissionResult(acceptance='unknown', transport=response.transport)
            )
            return
        if response.body is not None:
            evidence = await self.evidence_storage.save(response.body, call_id, context.lease.job_id)
            async with context.sessions() as db:
                await ProviderResponseService.register(
                    db,
                    context.lease,
                    call_id,
                    evidence,
                    http_status=response.http_status,
                )
        try:
            fact = ImageResponseService.parse(
                response.http_status,
                response.body,
                max_bytes=self.max_decoded_bytes,
                expected_count=payload.get('n', 1),
            )
        except ValueError:
            await context.record_submission(
                call_id,
                ProviderSubmissionResult(
                    acceptance='unknown',
                    transport='response',
                    httpStatus=response.http_status,
                ),
            )
            return
        stored = {}
        for image in fact.images:
            try:
                stored[image.ordinal] = await self.storage.persist(
                    image,
                    declared_format=fact.declared_format,
                    declared_size=fact.declared_size,
                )
            except (ValueError, OSError, ServiceWarning):
                fact.issues.append('IMAGE_ARCHIVE_FAILED')
        await context.record_images(call_id, fact, stored, http_status=response.http_status)

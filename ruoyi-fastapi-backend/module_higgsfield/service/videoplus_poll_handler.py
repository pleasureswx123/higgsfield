"""VideoPlus轮询处理器；网络等待与数据库事务严格分离。"""

from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.write_service import WriteService


class VideoPlusPollHandler:
    def __init__(
        self,
        *,
        credential_crypto: CredentialCryptoService | None = None,
        output_crypto: OutputSourceCryptoService | None = None,
    ) -> None:
        self.credential_crypto, self.output_crypto = credential_crypto, output_crypto

    async def __call__(self, context: JobExecutionContext) -> None:
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if job.kind != 'video' or job.orchestration_state != '4' or not job.upstream_task_id:
                WorkspaceService.conflict('PROVIDER_POLL_UNAVAILABLE', '任务不满足视频查询条件')
            job, _, _, version, config = await ProviderJobBindingService.require(db, context.lease, job)
            if config.adapter_version != 'videoplus-v1':
                WorkspaceService.conflict('PROVIDER_ADAPTER_UNSUPPORTED', '固定连接版本未选择VideoPlus适配器')
            transport = ProviderHttpService.from_versions(config, version, crypto=self.credential_crypto)
            task_id = job.upstream_task_id
            request_hash = WriteService.digest(
                {
                    'method': 'GET',
                    'operation': 'video_poll',
                    'upstreamTaskId': task_id,
                    'connectionVersionId': str(config.connection_version_id),
                    'credentialVersionId': str(version.credential_version_id),
                }
            )
            # 会话关闭会释放读取与配置锁；随后另一个短事务持久化查询意图。
        call_id = await context.begin_poll(request_hash)
        result = await transport.poll(task_id)
        await context.record_poll(
            call_id,
            http_status=result.http_status,
            body=result.body,
            transport=result.transport,
            crypto=self.output_crypto,
        )

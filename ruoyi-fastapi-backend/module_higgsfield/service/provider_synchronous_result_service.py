"""同步调用事实、生成输出和任务完成共用一次事务提交。"""

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSynchronousResult
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.output_discovery_service import OutputDiscoveryService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ProviderSynchronousResultService:
    @staticmethod
    async def record(
        db: AsyncSession,
        lease: JobLease,
        call_id: int,
        result: ProviderSynchronousResult,
        *,
        crypto: OutputSourceCryptoService | None = None,
    ) -> JobLease:
        try:
            job, now = await JobLeaseService.guard(db, lease)
            call = await ProviderCallDao.locked(db, call_id)
            if (
                call is None
                or call.job_id != job.job_id
                or call.credential_version_id != job.credential_version_id
                or call.state != '1'
                or call.operation not in {'image', 'video_submit'}
                or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
                or job.orchestration_state != '2'
            ):
                WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '响应不属于当前发送意图或任务状态已变化')
            job, now = await JobLeaseService.guard(db, lease)
            if any(item.kind != job.kind for item in result.outputs):
                WorkspaceService.conflict('OUTPUT_KIND_MISMATCH', '同步输出类型与任务类型不一致')
            call.state, call.acceptance = '2', 'accepted'
            call.http_status, call.response_id = result.http_status, result.response_id
            # 临时地址只进入输出密文，不复制到调用元数据。
            call.response_metadata = {'mode': 'synchronous', 'outputCount': len(result.outputs)}
            call.finished_time = now
            call.update_by, call.update_time = lease.worker, now
            job.upstream_response_id = result.response_id
            # 输出服务会重新读取租约；先刷入同一事务，避免刷新丢弃未刷新的字段。
            await db.flush()
            return await OutputDiscoveryService.record(db, lease, result.outputs, crypto=crypto, complete=True)
        except Exception:
            await db.rollback()
            raise

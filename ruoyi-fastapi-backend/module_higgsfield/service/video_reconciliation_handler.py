"""未知视频提交从已登记的加密原始响应恢复，不重新请求生成。"""

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.generation_worker_service import JobExecutionContext
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService


class VideoReconciliationHandler:
    def __init__(self, evidence_storage: ProviderResponseStorageService) -> None:
        self.evidence_storage = evidence_storage

    async def __call__(self, context: JobExecutionContext) -> None:
        saved = None
        async with context.sessions() as db:
            job, _ = await JobLeaseService.guard(db, context.lease)
            if job.kind != 'video' or job.orchestration_state != '3' or job.upstream_task_id is not None:
                raise ValueError('当前任务不是未知视频提交')
            call = await ProviderCallDao.submission(db, job.job_id)
            evidence = await ProviderResponseDao.for_call(db, call.call_id) if call else None
            if (
                call and call.state == '3' and call.operation == 'video_submit'
                and call.credential_version_id == job.credential_version_id
                and evidence and evidence.job_id == job.job_id
            ):
                saved = {
                    'call_id': call.call_id, 'job_id': job.job_id,
                    'evidence_id': evidence.response_evidence_id, 'http_status': evidence.http_status,
                    'files': {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')},
                }
        if saved is None:
            await context.defer(60)
            return
        # 文件校验、解密及解析均在数据库事务外执行。
        body = await self.evidence_storage.load(saved['files'], saved['call_id'], saved['job_id'])
        fact = VideoPlusResponseService.submission(saved['http_status'], body)
        if fact.acceptance == 'unknown':
            await context.defer(60)
            return
        await context.record_submission(
            saved['call_id'], fact, recovery_evidence_id=saved['evidence_id']
        )

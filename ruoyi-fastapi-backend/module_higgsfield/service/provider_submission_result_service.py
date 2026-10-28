"""调用响应与任务受理事实同事务提交，任何结果均不直接结算费用。"""

from dataclasses import replace
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ProviderSubmissionResultService:
    @staticmethod
    async def record(
        db: AsyncSession, lease: JobLease, call_id: int, result: ProviderSubmissionResult,
        *, recovery_evidence_id: int | None = None,
    ) -> JobLease:
        try:
            job, now = await JobLeaseService.guard(db, lease)
            call = await ProviderCallDao.locked(db, call_id)
            if (
                call is None
                or call.job_id != job.job_id
                or call.credential_version_id != job.credential_version_id
                or call.operation not in {'image', 'video_submit'}
            ):
                WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '响应不属于当前发送意图或任务状态已变化')
            if recovery_evidence_id is None:
                if (
                    call.state != '1'
                    or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
                    or job.orchestration_state != '2'
                ):
                    WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '响应发送版本已失效')
            else:
                evidence = await ProviderResponseDao.for_call(db, call_id)
                if (
                    type(recovery_evidence_id) is not int
                    or job.kind != 'video'
                    or call.operation != 'video_submit'
                    or job.orchestration_state != '3'
                    or job.upstream_task_id is not None
                    or call.state != '3'
                    or evidence is None
                    or evidence.response_evidence_id != recovery_evidence_id
                    or evidence.job_id != job.job_id
                    or evidence.http_status != result.http_status
                    or result.transport != 'response'
                    or result.acceptance != 'accepted'
                ):
                    WorkspaceService.conflict('RESPONSE_EVIDENCE_INVALID', '无法使用该响应证据恢复当前未知视频任务')
            job, now = await JobLeaseService.guard(db, lease)
            call.state = '3' if result.acceptance == 'unknown' else '2'
            call.acceptance = result.acceptance
            call.http_status, call.business_code = result.http_status, result.business_code
            call.response_id = result.response_id
            call.response_metadata = result.model_dump(by_alias=True, exclude_none=True)
            if recovery_evidence_id is not None:
                call.response_metadata = call.response_metadata | {'recoveryEvidenceId': str(recovery_evidence_id)}
            call.finished_time = now
            call.update_by, call.update_time = lease.worker, now
            if result.acceptance == 'accepted':
                job.orchestration_state, job.upstream_state = '4', '1'
                job.upstream_task_id = result.upstream_task_id
                job.next_action_time = now + timedelta(seconds=5)
            elif result.acceptance == 'rejected':
                job.orchestration_state, job.upstream_state = '5', '4'
                job.finished_time, job.next_action_time = now, None
            else:
                job.orchestration_state, job.upstream_state = '3', '6'
                job.next_action_time = now + timedelta(seconds=30)
            job.upstream_response_id = result.response_id
            job.lease_owner = None
            job.lease_until = None
            job.revision += 1
            job.event_sequence += 1
            job.update_by, job.update_time = lease.worker, now
            await JobEventDao.state(db, job, now, lease.worker)
            updated = replace(lease, revision=job.revision)
            await db.commit()
            return updated
        except Exception:
            await db.rollback()
            raise

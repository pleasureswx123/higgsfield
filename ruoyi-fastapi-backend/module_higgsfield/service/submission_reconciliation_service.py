"""依据已记录的查询证据恢复受理状态，不发起查询或自动重新提交。"""

from dataclasses import replace
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class SubmissionReconciliationService:
    @staticmethod
    async def record(db: AsyncSession, lease: JobLease, submission_id: int, evidence_call_id: int) -> JobLease:
        try:
            job, now = await JobLeaseService.guard(db, lease)
            original = await ProviderCallDao.locked(db, submission_id)
            evidence = await ProviderCallDao.locked(db, evidence_call_id)
            if (
                job.orchestration_state != '3'
                or job.upstream_task_id is not None
                or original is None
                or evidence is None
                or original.job_id != job.job_id
                or original.state != '3'
                or original.operation not in {'image', 'video_submit'}
                or original.credential_version_id != job.credential_version_id
                or evidence.call_id <= original.call_id
                or evidence.job_id != job.job_id
                or evidence.account_id != original.account_id
                or evidence.credential_version_id != original.credential_version_id
                or evidence.operation != 'video_poll'
                or evidence.state != '2'
                or evidence.request_metadata.get('submissionCallId') != str(submission_id)
                or evidence.request_metadata.get('fencingToken') != str(lease.fencing_token)
            ):
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '核查证据与原提交、账号或当前租约不一致')
            # 查询的HTTP成功不等于生成已受理，必须有适配器明确归一化的受理事实。
            try:
                fact = ProviderSubmissionResult.model_validate(evidence.response_metadata)
            except ValueError:
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '查询未记录有效的归一化受理事实')
            if (
                fact.transport != 'response'
                or fact.http_status != evidence.http_status
                or fact.response_id != evidence.response_id
                or fact.acceptance not in {'accepted', 'unknown'}
            ):
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '查询结果不能用于自动判定未受理或免费')
            job, now = await JobLeaseService.guard(db, lease)
            if fact.acceptance == 'accepted':
                job.orchestration_state, job.upstream_state = '4', '1'
                job.upstream_task_id = fact.upstream_task_id
                job.next_action_time = now + timedelta(seconds=5)
                job.revision += 1
                job.event_sequence += 1
                await JobEventDao.state(db, job, now, lease.worker)
            else:
                job.next_action_time = now + timedelta(seconds=30)
            # 查询事实保留在独立调用记录，不覆盖最初未收到响应的历史事实或响应ID。
            job.lease_owner, job.lease_until = None, None
            job.update_by, job.update_time = lease.worker, now
            updated = replace(lease, revision=job.revision)
            await db.commit()
            return updated
        except Exception:
            await db.rollback()
            raise

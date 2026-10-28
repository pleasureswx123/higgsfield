"""人工确认使用已保存的明确拒绝证据，不覆盖最初未知调用事实。"""
import re
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.dao.incident_rejection_dao import IncidentRejectionDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class IncidentRejectionService:
    @staticmethod
    def eligible(job, now):
        return (job.orchestration_state in {'3', '6'} and not job.upstream_task_id
                and job.upstream_state in {'0', '6'}
                and (job.lease_until is None or job.lease_until <= now))

    @staticmethod
    def validate_evidence(job, original, evidence):
        valid = (original is not None and evidence is not None
                 and original.job_id == job.job_id and original.operation in {'image', 'video_submit'}
                 and original.state == '3' and original.acceptance == 'unknown'
                 and original.credential_version_id == job.credential_version_id
                 and evidence.call_id > original.call_id and evidence.job_id == job.job_id
                 and evidence.account_id == original.account_id
                 and evidence.credential_version_id == original.credential_version_id
                 and evidence.operation == 'video_poll' and evidence.state == '2'
                 and evidence.request_metadata.get('submissionCallId') == str(original.call_id))
        if not valid:
            WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '证据与原提交、任务、账号或凭据版本不一致')
        try:
            fact = ProviderSubmissionResult.model_validate(evidence.response_metadata)
        except ValueError:
            WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '证据缺少规范化受理结果')
        if (fact.acceptance != 'rejected' or fact.transport != 'response'
                or fact.http_status != evidence.http_status or fact.response_id != evidence.response_id
                or fact.business_code != evidence.business_code):
            WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '证据不能证明明确未受理')

    @classmethod
    async def confirm(cls, db, user, identity, payload, key):
        path, prefix = f'/generation-incidents/{identity}/actions', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            job = await GenerationReadDao.job(db, identity, lock='write')
            if job is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或不在管理范围内')
            await AdminScopeService.project(db, user, job.project_id, 'operations:recover')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(job, payload.revision)
            now = await JobLeaseDao.now(db)
            if not cls.eligible(job, now):
                WorkspaceService.conflict('INCIDENT_CONFIRM_UNAVAILABLE', '仅可核实无有效租约且没有上游任务编号的未知提交')
            match = re.fullmatch(r'provider-call:([1-9][0-9]{0,18})', payload.evidence_ref or '')
            if not match or int(match[1]) > 9223372036854775807:
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_INVALID', '必须引用已记录的 provider-call 调用证据')
            original = await ProviderCallDao.submission(db, identity)
            evidence = await ProviderCallDao.locked(db, int(match[1]))
            cls.validate_evidence(job, original, evidence)
            if await IncidentRejectionDao.contradictory(db, identity):
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_CONFLICT', '存在受理、输出或多次提交事实，不能确认未受理')
            before = {'orchestrationState': job.orchestration_state, 'upstreamState': job.upstream_state}
            job.orchestration_state, job.upstream_state = '5', '4'
            job.finished_time, job.next_action_time = now, None
            job.lease_owner, job.lease_until = None, None
            job.fencing_token += 1
            job.revision += 1
            job.event_sequence += 1
            job.update_time, job.update_by = now, user.user.user_name
            await JobEventDao.state(db, job, now, user.user.user_name)
            receipt = {'jobId': str(identity), 'revision': str(job.revision), 'accepted': True,
                       'action': 'confirm_not_accepted', 'acceptance': 'rejected'}
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user', project_id=job.project_id,
                object_type='creation_job', object_id=str(identity), action='confirm_not_accepted', reason=payload.reason,
                request_id=WriteService.digest({'prefix': prefix, 'path': path, 'key': key}),
                before_after={'before': before, 'after': receipt, 'evidenceRef': payload.evidence_ref},
                **WriteService.audit(user)))
            return await WriteService.finish(db, user, path, key, data, receipt, 'generation', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise

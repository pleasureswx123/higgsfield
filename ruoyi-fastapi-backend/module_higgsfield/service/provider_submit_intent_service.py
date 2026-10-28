"""先持久化发送意图再进行外部请求，未知提交不创建新发送记录。"""

import re
from dataclasses import replace

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.generation_access_service import GenerationAccessService
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService


class ProviderSubmitIntentService:
    @staticmethod
    async def begin(db: AsyncSession, lease: JobLease, request_hash: str) -> tuple[JobLease, int]:
        if not isinstance(request_hash, str) or not re.fullmatch('[0-9a-f]{64}', request_hash):
            raise ValueError('请求摘要必须是规范请求的SHA256，不接收请求正文或授权头')
        try:
            job, now = await JobLeaseService.guard(db, lease)
            if (
                job.orchestration_state != '1'
                or job.upstream_state != '0'
                or job.upstream_task_id
                or job.upstream_response_id
            ):
                WorkspaceService.conflict('PROVIDER_SUBMIT_UNAVAILABLE', '任务当前阶段不允许新建提交意图')
            if await ProviderCallDao.submission(db, job.job_id):
                WorkspaceService.conflict('PROVIDER_SUBMIT_EXISTS', '已有提交调用，必须核查原请求')
            # 与项目治理共用行锁：暂停/归档若先提交，不能再记录新的发送意图。
            # 已提交意图及已受理任务的后续查询、归档不经过此门槛。
            await GenerationAccessService.require(db, job)
            job, now, account, version, config = await ProviderJobBindingService.require(db, lease, job)
            operation = {'image': 'image', 'video': 'video_submit'}.get(job.kind)
            if operation is None:
                WorkspaceService.conflict('PROVIDER_SUBMIT_UNAVAILABLE', '当前任务类型未开放发送')
            call = await ProviderCallDao.add(
                db,
                {
                    'job_id': job.job_id,
                    'account_id': account.account_id,
                    'credential_version_id': version.credential_version_id,
                    'operation': operation,
                    'request_hash': request_hash,
                    'state': '1',
                    'acceptance': 'unknown',
                    'request_metadata': {
                        'connectionVersionId': str(config.connection_version_id),
                        'adapterVersion': config.adapter_version,
                        'modelVersionId': str(job.model_version_id),
                        'fencingToken': str(lease.fencing_token),
                    },
                    'started_time': now,
                    'create_by': lease.worker,
                    'update_by': lease.worker,
                    'create_time': now,
                    'update_time': now,
                },
            )
            job.orchestration_state = '2'
            job.revision += 1
            job.event_sequence += 1
            job.update_by, job.update_time = lease.worker, now
            await JobEventDao.state(db, job, now, lease.worker)
            result = replace(lease, revision=job.revision), call.call_id
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

"""当前发送租约下登记不可变响应证据，不改变任务完成或计费状态。"""

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.entity.vo.provider_response_vo import ResponseFileFacts
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService

HTTP_MIN, HTTP_MAX = 100, 599


class ProviderResponseService:
    @staticmethod
    async def register(db: AsyncSession, lease: JobLease, call_id: int, facts: dict, *, http_status: int) -> int:
        file = ResponseFileFacts.model_validate(facts)
        if type(http_status) is not int or not HTTP_MIN <= http_status <= HTTP_MAX:
            raise ValueError('响应证据HTTP状态无效')
        try:
            job, _ = await JobLeaseService.guard(db, lease)
            call = await ProviderCallDao.locked(db, call_id)
            if (
                job.kind not in {'image', 'video'}
                or job.orchestration_state != '2'
                or call is None
                or call.job_id != job.job_id
                or call.operation != {'image': 'image', 'video': 'video_submit'}[job.kind]
                or call.state != '1'
                or call.credential_version_id != job.credential_version_id
                or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
            ):
                WorkspaceService.conflict('PROVIDER_RESPONSE_STALE', '响应证据不属于当前生成发送意图')
            job, now = await JobLeaseService.guard(db, lease)
            previous = await ProviderResponseDao.for_call(db, call_id)
            values = file.model_dump() | {'job_id': job.job_id, 'http_status': http_status}
            if previous is not None:
                if any(getattr(previous, key) != value for key, value in values.items()):
                    WorkspaceService.conflict('RESPONSE_EVIDENCE_IMMUTABLE', '原始响应证据不能被其他文件覆盖')
                identity = previous.response_evidence_id
            else:
                row = await ProviderResponseDao.add(
                    db,
                    values
                    | {
                        'provider_call_id': call_id,
                        'create_by': lease.worker,
                        'update_by': lease.worker,
                        'create_time': now,
                        'update_time': now,
                    },
                )
                identity = row.response_evidence_id
            await db.commit()
            return identity
        except Exception:
            await db.rollback()
            raise

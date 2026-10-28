"""短事务领取与续租，不执行供应商调用，不将过期提交自动重发。"""

from dataclasses import dataclass
from datetime import timedelta
import re
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.preparation_diagnostic_service import PreparationDiagnosticService


@dataclass(frozen=True)
class JobLease:
    job_id: int
    worker: str
    fencing_token: int
    revision: int
    action: str


class JobLeaseService:
    @staticmethod
    def validate_worker(worker):
        if not isinstance(worker, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}', worker):
            raise ValueError('执行实例名称必须为最多64位安全标识')

    @staticmethod
    def validate_duration(seconds):
        if type(seconds) is not int or not 5 <= seconds <= 300:
            raise ValueError('租约时长必须为5到300秒')

    @classmethod
    async def claim(cls, db, worker, *, limit=10, lease_seconds=60, kinds=None):
        """调用方提供专用短事务会话；返回后事务已提交，可以开始外部工作。"""
        cls.validate_worker(worker)
        cls.validate_duration(lease_seconds)
        if kinds is not None and (not isinstance(kinds, tuple) or not kinds or set(kinds) - {'image', 'video', 'chat'}):
            raise ValueError('任务类型筛选必须是非空的受支持类型元组')
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('单次领取数量必须为1到100')
        try:
            now = await JobLeaseDao.now(db)
            rows = await JobLeaseDao.candidates(db, now, limit, kinds)
            leases = []
            for row in rows:
                row.lease_owner = worker
                row.lease_until = now + timedelta(seconds=lease_seconds)
                row.fencing_token += 1
                row.attempt_count += 1
                if row.orchestration_state == '2':
                    # 提交阶段失去租约不能证明上游没有受理，必须进入核查。
                    calls = await ProviderCallDao.sending_submissions(db, row.job_id)
                    recovered_at = await JobLeaseDao.now(db)
                    for call in calls:
                        call.state, call.acceptance = '3', 'unknown'
                        call.finished_time = recovered_at
                        call.update_time, call.update_by = recovered_at, worker
                        # 未观察到响应，不能推断超时、拒绝或成功，也不能覆盖原始请求证据。
                        call.response_metadata = {'recoveryReason': 'submission_lease_lost'}
                    row.orchestration_state = '3'
                    row.upstream_state = '6'
                    row.revision += 1
                    row.event_sequence += 1
                    row.update_time, row.update_by = now, worker
                    await JobLeaseDao.recovery_event(db, row, now, worker)
                action = {'0': 'prepare', '1': 'prepare', '3': 'reconcile_submission', '4': 'poll'}[
                    row.orchestration_state
                ]
                leases.append(JobLease(row.job_id, worker, row.fencing_token, row.revision, action))
            await db.commit()
            return leases
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def guard(cls, db, lease, *, expected_revision=None):
        """在结果写入事务内锁任务并验证当前租约；调用方随后同事务更新状态及事件。"""
        cls.validate_worker(lease.worker)
        row = await JobLeaseDao.owned(db, lease.job_id, lease.worker, lease.fencing_token)
        now = await JobLeaseDao.now(db)
        if row is None or row.lease_until is None or row.lease_until <= now:
            WorkspaceService.conflict('JOB_LEASE_LOST', '执行租约已失效，旧执行者不能写回结果')
        revision = lease.revision if expected_revision is None else expected_revision
        if row.revision != revision:
            WorkspaceService.conflict('JOB_REVISION_CHANGED', '任务已发生并发变化，需重新核对当前状态')
        return row, now

    @classmethod
    async def renew(cls, db, lease, *, lease_seconds=60):
        cls.validate_duration(lease_seconds)
        try:
            row, now = await cls.guard(db, lease)
            row.lease_until = now + timedelta(seconds=lease_seconds)
            until = row.lease_until
            await db.commit()
            return until
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def release(cls, db, lease, *, retry_after_seconds, diagnostic_code=None):
        if type(retry_after_seconds) is not int or not 0 <= retry_after_seconds <= 86400:
            raise ValueError('调度延迟必须为0到86400秒')
        try:
            row, now = await cls.guard(db, lease, expected_revision=lease.revision)
            if diagnostic_code is not None:
                await PreparationDiagnosticService.record(db, row, now, lease.worker, diagnostic_code)
            row.lease_owner = None
            row.lease_until = None
            row.next_action_time = now + timedelta(seconds=retry_after_seconds)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

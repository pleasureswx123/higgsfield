"""工作进程短事务状态推进；外部调用必须在事务提交后进行。"""

from dataclasses import replace
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class JobTransitionService:
    MAX_DELAY_SECONDS = 86400
    MAX_UPSTREAM_ID_LENGTH = 255
    FIRST_PRINTABLE_CODEPOINT = 32

    @classmethod
    async def apply(
        cls,
        db: AsyncSession,
        lease: JobLease,
        *,
        action: str,
        upstream_task_id: str | None = None,
        retry_after_seconds: int = 5,
    ) -> JobLease:
        """仅接受适配器已归一化的事实，不接收原始响应、密钥或任意状态字典。

        返回的新租约包含新 revision；进入提交阶段保留租约供外部调用后写回。
        未知提交不开放自动重发，后续核查只能写入确实已受理的事实。
        本方法不修改费用、预占、归档或固定输入快照。
        生成成功须调用 OutputDiscoveryService.record(complete=True)，与输出事实原子提交。
        """
        actions = {
            'prepare',
            'submit',
            'unknown',
            'accepted',
            'running',
            'failed',
            'cancelled',
            'rejected',
            'block',
        }
        if action not in actions:
            raise ValueError('不支持的任务推进动作')
        if type(retry_after_seconds) is not int or not 0 <= retry_after_seconds <= cls.MAX_DELAY_SECONDS:
            raise ValueError('调度延迟必须为0到86400秒')
        if upstream_task_id is not None and (
            not isinstance(upstream_task_id, str)
            or not upstream_task_id.strip()
            or len(upstream_task_id) > cls.MAX_UPSTREAM_ID_LENGTH
            or any(ord(char) < cls.FIRST_PRINTABLE_CODEPOINT for char in upstream_task_id)
        ):
            raise ValueError('上游任务编号无效')
        try:
            row, now = await JobLeaseService.guard(db, lease)
            source = row.orchestration_state
            allowed = {
                'prepare': {'0'},
                'submit': {'1'},
                'block': {'1'},
                'unknown': {'2'},
                'accepted': {'2', '3'},
                'rejected': {'2'},
                'running': {'4'},
                'failed': {'4'},
                'cancelled': {'4'},
            }
            if source not in allowed[action]:
                WorkspaceService.conflict('JOB_TRANSITION_INVALID', '当前任务阶段不允许该推进动作')
            if action == 'accepted' and not upstream_task_id:
                WorkspaceService.conflict('JOB_UPSTREAM_ID_REQUIRED', '确认受理必须保存上游任务编号')
            if upstream_task_id is not None and action != 'accepted':
                raise ValueError('只有确认受理动作可以绑定上游任务编号')
            if row.upstream_task_id and upstream_task_id and row.upstream_task_id != upstream_task_id:
                WorkspaceService.conflict('JOB_UPSTREAM_ID_CHANGED', '已绑定的上游任务编号不能替换')
            transitions = {
                'prepare': ('1', '0'),
                'submit': ('2', '0'),
                'block': ('6', '0'),
                'unknown': ('3', '6'),
                'accepted': ('4', '1'),
                'running': ('4', '2'),
                'failed': ('5', '4'),
                'cancelled': ('5', '5'),
                'rejected': ('5', '4'),
            }
            target, upstream = transitions[action]
            changed = (row.orchestration_state, row.upstream_state) != (target, upstream)
            row.orchestration_state, row.upstream_state = target, upstream
            if upstream_task_id:
                row.upstream_task_id = upstream_task_id
            row.next_action_time = None if target in {'5', '6'} else now + timedelta(seconds=retry_after_seconds)
            if target == '5':
                row.finished_time = now
            # 提交前后连续工作保留租约；轮询与核查通过下一轮领取推进。
            if action not in {'prepare', 'submit'}:
                row.lease_owner = None
                row.lease_until = None
            row.update_time, row.update_by = now, lease.worker
            if changed:
                row.revision += 1
                row.event_sequence += 1
                await JobEventDao.state(db, row, now, lease.worker)
            updated = replace(lease, revision=row.revision)
            await db.commit()
            return updated
        except Exception:
            await db.rollback()
            raise

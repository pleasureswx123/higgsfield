"""明确未提交的本地取消释放原周期预占，不按当前日期重新选预算。"""

from decimal import Decimal, localcontext
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from module_higgsfield.entity.do.budget_do import HfBudgetLedgerEntry
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class BudgetReleaseService:
    @staticmethod
    async def release_unsubmitted(db, user, job_id, *, reason):
        """仅供已授权取消事务调用；调用方先写本地取消事实，再同事务调用并提交。

        此方法不提交事务，保存点使任一周期失败时全部释放撤销。
        只有编排结束、上游从未提交且取消已确认可释放；失败、未知和上游取消均不满足。
        """
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise ValueError('释放原因必须为1至4000个非空字符')
        async with db.begin_nested():
            job, periods, reservations = await BudgetReservationDao.release_context(db, job_id)
            if (
                job is None
                or (job.orchestration_state, job.upstream_state, job.cancel_state) != ('5', '0', '2')
                or job.upstream_task_id is not None
                or job.upstream_response_id is not None
            ):
                WorkspaceService.conflict('BUDGET_RELEASE_UNCONFIRMED', '只有明确未提交的本地取消任务可以释放预占')
            audit = WriteService.audit(user)
            result = []
            with localcontext() as context:
                context.prec = 100
                for reservation in reservations:
                    period = periods.get(reservation.period_id)
                    if period is None:
                        WorkspaceService.conflict('BUDGET_PERIOD_MISSING', '原预占预算周期缺失')
                    if reservation.state == '3' and reservation.remaining_amount == 0:
                        result.append(str(reservation.reservation_id))
                        continue
                    if (
                        reservation.state not in {'0', '4'}
                        or reservation.remaining_amount != reservation.original_amount
                    ):
                        WorkspaceService.conflict(
                            'BUDGET_RELEASE_CONFLICT', '预占已有结算或部分释放，不能按未提交任务释放'
                        )
                    amount = reservation.remaining_amount
                    if period.reserved_amount < amount:
                        WorkspaceService.conflict('BUDGET_BALANCE_INCONSISTENT', '预算预占缓存与原始预占不一致')
                    reservation.remaining_amount = Decimal(0)
                    reservation.state = '3'
                    reservation.revision += 1
                    reservation.update_by, reservation.update_time = audit['update_by'], audit['update_time']
                    if amount:
                        period.reserved_amount -= amount
                        period.revision += 1
                        period.update_by, period.update_time = audit['update_by'], audit['update_time']
                        await BudgetReservationDao.add(
                            db,
                            HfBudgetLedgerEntry,
                            period_id=period.period_id,
                            reservation_id=reservation.reservation_id,
                            business_event_key=f'job:{job_id}:local-cancel',
                            entry_type='release',
                            reserved_delta=-amount,
                            consumed_delta=Decimal(0),
                            limit_delta=Decimal(0),
                            reason=reason.strip(),
                            **audit,
                        )
                    result.append(str(reservation.reservation_id))
                await db.flush()
            return result

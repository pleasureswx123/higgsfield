"""费用调整事务组件：外层先授权、锁任务，并提交审计、预算和通知。"""

from decimal import Decimal, localcontext
from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao
from module_higgsfield.entity.do.billing_do import HfBillingAdjustment
from module_higgsfield.entity.vo.billing_adjustment_vo import BillingAdjustmentInput
from module_higgsfield.service.project_workspace_service import WorkspaceService


class BillingAdjustmentService:
    @staticmethod
    async def append(db, *, job, event_id, payload: BillingAdjustmentInput, business_key, actor_id, now, actor,
                     cost_center_id=None):
        """只追加，不独立提交；重复业务键必须保持金额、原因和用量依据一致。"""
        if not isinstance(business_key, str) or not business_key.strip() or len(business_key) > 200:
            raise ValueError('调整业务键无效')
        if type(actor_id) is not int or not 0 < actor_id <= 9223372036854775807:
            raise ValueError('调整操作者无效')
        reconciliation_id = int(payload.reconciliation_line_id) if payload.reconciliation_line_id else None
        initial = await BillingDao.context(db, event_id)
        if initial is None:
            WorkspaceService.conflict('BILLING_EVENT_NOT_FOUND', '费用事件不存在')
        if reconciliation_id is not None:
            # 与账单导入、确认保持账号锁先于对象锁的顺序，避免交叉等待。
            await ReconciliationDao.lock_account(db, initial[1].account_id)
        # 与计价工作器保持对象先于费用事件的加锁顺序。
        subject = await BillingDao.subject(db, initial[1].subject_id)
        event = await BillingDao.event_by_id(db, event_id)
        if event is None:
            WorkspaceService.conflict('BILLING_EVENT_NOT_FOUND', '费用事件不存在')
        if subject is None or event.subject_id != subject.subject_id or (
            subject.job_id != job.job_id if job is not None else
            subject.job_id is not None or cost_center_id is None or subject.cost_center_id != cost_center_id
        ):
            WorkspaceService.conflict('BILLING_EVENT_NOT_FOUND', '费用事件不属于已授权任务或成本中心')
        delta = Decimal(payload.delta_amount)
        usage_id = int(payload.usage_record_id) if payload.usage_record_id else None
        existing = await BillingDao.adjustment_by_key(db, event_id, business_key)
        if existing is not None:
            if (
                existing.delta_amount != delta
                or existing.reason != payload.reason
                or existing.usage_record_id != usage_id
                or existing.reconciliation_line_id != reconciliation_id
                or existing.actor_id != actor_id
            ):
                WorkspaceService.conflict('IDEMPOTENCY_KEY_REUSED', '调整业务键已用于不同内容')
            return existing, False
        WorkspaceService.check_revision(event, payload.revision)
        if event.amount is None:
            WorkspaceService.conflict('BILLING_AMOUNT_UNKNOWN', '未知费用不能通过差额调整推定原始金额')
        if reconciliation_id is not None:
            evidence = await ReconciliationDao.line_by_id(db, reconciliation_id, lock=True)
            if (
                evidence is None
                or evidence.status != '2'
                or evidence.account_id != subject.account_id
                or evidence.subject_id != subject.subject_id
                or (evidence.accepted_currency or evidence.currency) != event.currency
            ):
                WorkspaceService.conflict('BILLING_RECONCILIATION_MISMATCH', '对账依据必须已确认且属于同一账号、计费对象和币种')
        if usage_id is not None:
            usage = await BillingDao.adopted_usage(db, usage_id)
            if usage is None or usage.subject_id != event.subject_id:
                WorkspaceService.conflict('BILLING_USAGE_MISMATCH', '用量依据不属于当前计费对象')
        with localcontext() as context:
            context.prec = 100
            effective = event.amount + await BillingDao.adjustment_total(db, event_id) + delta
            if not effective.is_finite() or effective < 0 or effective >= Decimal('100000000000000'):
                WorkspaceService.conflict('BILLING_ADJUSTMENT_RANGE', '调整后金额不能为负或超过存储范围')
        row = await BillingDao.add(
            db,
            HfBillingAdjustment,
            dict(
                event_id=event_id,
                usage_record_id=usage_id,
                reconciliation_line_id=reconciliation_id,
                adjustment_key=business_key,
                delta_amount=delta,
                reason=payload.reason,
                actor_id=actor_id,
                create_by=actor,
                update_by=actor,
                create_time=now,
                update_time=now,
            ),
        )
        event.revision += 1
        event.update_by, event.update_time = actor, now
        await db.flush()
        return row, True

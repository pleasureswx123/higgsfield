"""项目费用查询与调整：授权、幂等、预算、审计与任务通知同事务。"""

from decimal import Decimal, localcontext
from common.vo import PageModel
from exceptions.exception import PermissionException

from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.billing_adjustment_service import BillingAdjustmentService
from module_higgsfield.service.budget_settlement_service import BudgetSettlementService
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class BillingAdminService:
    @staticmethod
    async def listing(db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'billing:read')
        if query.scope == 'cost_center' and not any(role['data_scope'] == '1' for role in roles):
            raise PermissionException(message='成本中心费用读取要求全部管理范围')
        if query.purpose == 'procurement' and not any(role['data_scope'] == '1' for role in roles):
            raise PermissionException(message='采购费用读取当前要求全部管理范围')
        rows, total = await BillingDao.page(db, actor, roles, query)
        result = []
        with localcontext() as context:
            context.prec = 100
            for row in rows:
                result.append(
                    {
                        'id': str(row['event_id']),
                        'subjectId': str(row['subject_id']),
                        'jobId': str(row['job_id']) if row['job_id'] is not None else None,
                        'costCenterId': str(row['cost_center_id']) if row['cost_center_id'] is not None else None,
                        'purpose': row['purpose'],
                        'currency': row['currency'],
                        'amount': None if row['amount'] is None else format(row['amount'], '.10f'),
                        'effectiveAmount': None
                        if row['amount'] is None
                        else format(row['amount'] + row['adjustment_total'], '.10f'),
                        'state': ('pending', 'calculated', 'confirmed', 'disputed')[int(row['state'])],
                        'revision': str(row['revision']),
                        'createTime': row['create_time'].isoformat(),
                    }
                )
        return PageModel(
            rows=result,
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @staticmethod
    async def authorize(db, user, identity, permission):
        await AdminScopeService.context(db, user, permission)
        scope = await BillingDao.context(db, identity)
        if scope is None:
            WorkspaceService.conflict('BILLING_EVENT_NOT_FOUND', '项目费用事件不存在或不在管理范围内')
        event, subject = scope
        if subject.job_id is None:
            await AdminScopeService.global_access(db, user, permission)
            await BillingDao.refresh(db, event)
            return None, subject, event
        job = await BillingDao.job(db, subject.job_id, skip_locked=False)
        if job is None:
            WorkspaceService.conflict('BILLING_EVENT_NOT_FOUND', '费用所属任务不存在')
        await AdminScopeService.project(db, user, job.project_id, permission)
        if event.purpose == 'procurement':
            await AdminScopeService.global_access(db, user, permission)
        await BillingDao.refresh(db, event)
        return job, subject, event

    @classmethod
    async def detail(cls, db, user, identity):
        job, subject, event = await cls.authorize(db, user, identity, 'billing:read')
        lines = await BillingDao.lines(db, identity)
        adjustments = await BillingDao.adjustments(db, identity)
        usage = await BillingDao.adopted_usage(db, event.usage_record_id)
        if usage is not None and usage.subject_id != subject.subject_id:
            WorkspaceService.conflict('BILLING_USAGE_MISMATCH', '费用采用用量的对象归属不一致')
        effective = None
        if event.amount is not None:
            with localcontext() as context:
                context.prec = 100
                effective = format(event.amount + sum((row.delta_amount for row in adjustments), Decimal(0)), '.10f')
        quantities = {}
        if usage is not None:
            for key, column in (
                ('inputTokens', 'input_tokens'),
                ('outputTokens', 'output_tokens'),
                ('videoTokens', 'video_tokens'),
                ('imageCount', 'image_count'),
                ('outputSeconds', 'output_seconds'),
                ('referenceSeconds', 'reference_seconds'),
            ):
                value = getattr(usage, column)
                quantities[key] = None if value is None else value if key == 'imageCount' else str(value)
        return {
            'id': str(event.event_id),
            'subjectId': str(subject.subject_id),
            'jobId': str(job.job_id) if job else None,
            'costCenterId': str(subject.cost_center_id) if subject.cost_center_id is not None else None,
            'purpose': event.purpose,
            'currency': event.currency,
            'amount': None if event.amount is None else format(event.amount, '.10f'),
            'effectiveAmount': effective,
            'state': ('pending', 'calculated', 'confirmed', 'disputed')[int(event.state)],
            'revision': str(event.revision),
            'priceVersionId': str(event.price_version_id),
            'createTime': event.create_time.isoformat(),
            'usageState': usage.completeness if usage else 'unknown',
            'usage': quantities,
            'lines': [
                {
                    'id': str(row.line_item_id),
                    'itemCode': row.calculation_snapshot.get('itemCode'),
                    'quantity': format(row.quantity, 'f'),
                    'unitQuantity': format(row.unit_quantity, 'f'),
                    'unitPrice': format(row.unit_price, '.10f'),
                    'amount': format(row.amount, '.10f'),
                }
                for row in lines
            ],
            'adjustments': [
                {
                    'id': str(row.adjustment_id),
                    'deltaAmount': format(row.delta_amount, '.10f'),
                    'reason': row.reason,
                    'reconciliationLineId': str(row.reconciliation_line_id) if row.reconciliation_line_id else None,
                    'createTime': row.create_time.isoformat(),
                }
                for row in adjustments
            ],
        }

    @staticmethod
    async def adjust(db, user, identity, payload, key):
        path, prefix = f'/billing-events/{identity}/adjustments', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.context(db, user, 'billing:adjust')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            job, subject, event = await BillingAdminService.authorize(db, user, identity, 'billing:adjust')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            row, changed = await BillingAdjustmentService.append(
                db,
                job=job,
                event_id=identity,
                payload=payload,
                business_key=f'manual:{identity}:revision:{payload.revision}',
                actor_id=user.user.user_id,
                now=audit['update_time'],
                actor=user.user.user_name,
                cost_center_id=subject.cost_center_id if job is None else None,
            )
            # 使用数据库实际毫秒时间，保证永久业务键重放与首个响应一致。
            await BillingDao.refresh(db, row)
            result = {
                'id': str(row.adjustment_id),
                'eventId': str(identity),
                'deltaAmount': format(row.delta_amount, '.10f'),
                'currency': event.currency,
                'createTime': row.create_time.isoformat(),
            }
            if changed and job is not None:
                await BudgetSettlementService.settle(
                    db, job.job_id, now=audit['update_time'], worker=user.user.user_name
                )
                job.revision += 1
                job.event_sequence += 1
                job.update_by, job.update_time = user.user.user_name, audit['update_time']
                await JobEventDao.usage(
                    db,
                    job,
                    audit['update_time'],
                    user.user.user_name,
                    await GenerationReadService.usage_state(db, job.job_id),
                )
            if changed:
                await PriceSourceDao.audit(
                    db,
                    dict(
                        actor_id=user.user.user_id,
                        actor_kind='user',
                        project_id=job.project_id if job is not None else None,
                        object_type='billing_event',
                        object_id=str(identity),
                        action='adjust',
                        request_id=WriteService.digest({'path': path, 'key': key}),
                        before_after={'adjustment': result, 'reason': payload.reason,
                            'costCenterId': str(subject.cost_center_id) if subject.cost_center_id is not None else None},
                        **audit,
                    ),
                )
            return await WriteService.finish(
                db, user, path, key, data, result, 'billing_adjustment', row.adjustment_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

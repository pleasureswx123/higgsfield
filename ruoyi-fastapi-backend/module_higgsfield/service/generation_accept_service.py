"""任务、预算预占、事件及幂等回执原子受理；不发送供应商请求。"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.dao.generation_accept_dao import GenerationAcceptDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.budget_reservation_service import BudgetReservationService
from module_higgsfield.service.generation_preparation_service import GenerationPreparationService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.response_util import ResponseUtil


class GenerationAcceptService:
    @staticmethod
    def receipt(job_id: int) -> dict:
        return {
            'id': str(job_id),
            'resourceType': 'generation',
            'status': 'accepted',
            'statusUrl': f'/api/v1/generations/{job_id}',
            'eventsUrl': f'/api/v1/generations/{job_id}/events',
            'revision': '1',
        }

    @classmethod
    async def accept(
        cls,
        db: AsyncSession,
        user: CurrentUserModel,
        payload: GenerationInput,
        key: str,
        *,
        currencies: dict[str, str],
        missing_budget_policy: str,
    ) -> tuple:
        if not key or missing_budget_policy not in ('allow', 'reject'):
            raise ValueError('受理必须提供幂等键及明确无预算策略')
        path = '/generations'
        data = payload.model_dump(by_alias=True)
        digest = WriteService.digest({'prefix': '/api/v1', 'method': 'POST', 'path': path, 'key': key})
        try:
            await WriteService.lock(db, user, path, key)
            await WorkspaceService.authorize(db, user, int(payload.project_id), 'generation:create')
            existing = await GenerationAcceptDao.existing(db, user.user.user_id, int(payload.project_id), digest)
            if existing:
                if existing.request_hash != WriteService.digest(data):
                    WorkspaceService.conflict('IDEMPOTENCY_KEY_REUSED', '原幂等键已用于其他生成内容')
                await db.commit()
                return json.loads(ResponseUtil.success(data=cls.receipt(existing.job_id)).body), True
            if await WriteService.replay(db, user, path, key, data):
                WorkspaceService.conflict('GENERATION_RECEIPT_INCONSISTENT', '受理回执缺少对应任务，请联系管理员核查')
            prepared = await GenerationPreparationService.prepare(db, user, payload, currencies=currencies)
            now = prepared['acceptedAt']
            department = user.user.dept
            audit = WriteService.audit(user)
            snapshot = {
                **prepared['inputSnapshot'],
                'route': prepared['route'],
                'prices': prepared['prices'],
                'estimate': prepared['estimate'],
            }
            job = await GenerationAcceptDao.create(
                db,
                {
                    'project_id': int(payload.project_id),
                    'actor_id': user.user.user_id,
                    'dept_id': user.user.dept_id,
                    'department_snapshot': department.model_dump(by_alias=True, mode='json') if department else {},
                    'kind': payload.kind,
                    'idempotency_key': digest,
                    'request_hash': WriteService.digest(data),
                    'model_version_id': int(prepared['modelVersionId']),
                    'model_variant_id': int(prepared['modelVariantId']),
                    'credential_version_id': int(prepared['route']['credentialVersionId']),
                    'platform_price_version_id': int(prepared['prices']['platform']['priceVersionId']),
                    'procurement_price_version_id': int(prepared['prices']['procurement']['priceVersionId']),
                    'input_snapshot': snapshot,
                    'event_sequence': 1,
                    'next_action_time': now,
                },
                prepared['inputSnapshot']['compiled'],
                audit,
            )
            estimates = {
                (purpose, value['currency']): value['total']
                for purpose, value in prepared['estimate']['estimates'].items()
            }
            reservations = await BudgetReservationService.reserve(
                db,
                user,
                job_id=job.job_id,
                project_id=job.project_id,
                at=now,
                estimates=estimates,
                missing_budget_policy=missing_budget_policy,
            )
            # 零额预占不产生零变动账本，但仍须保留固定汇率以供后续真实费用结算。
            job.input_snapshot = {**snapshot, 'budgetReservations': reservations}
            await JobEventDao.state(db, job, now, user.user.user_name)
            return await WriteService.finish(
                db, user, path, key, data, cls.receipt(job.job_id), 'generation', job.job_id
            )
        except Exception:
            await db.rollback()
            raise

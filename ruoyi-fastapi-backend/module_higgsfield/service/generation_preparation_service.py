"""受理和输入检查共享固定输入、路由与实际计价版本，事务由调用方管理。"""

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_input_service import GenerationInputService
from module_higgsfield.service.generation_price_service import GenerationPriceService
from module_higgsfield.service.generation_route_service import GenerationRouteService


class GenerationPreparationService:
    @staticmethod
    async def prepare(
        db: AsyncSession,
        user: CurrentUserModel,
        payload: GenerationInput,
        *,
        currencies: dict[str, str],
        tokens: EstimateTokenService | None = None,
    ) -> dict:
        route = await GenerationRouteService.select(db, user, int(payload.project_id), int(payload.model_version_id))
        prepared = await GenerationInputService.prepare(db, user, payload)
        now = await JobLeaseDao.now(db)
        prices = await GenerationPriceService.freeze(
            db,
            variant_id=int(prepared['modelVariantId']),
            account_id=int(route['accountId']),
            currencies=currencies,
            at=now,
        )
        # 新任务只固定实际计价依据，不预测Token、不预占预算。
        estimate = {'mode': 'actual_usage', 'estimates': {}}
        return {**prepared, 'route': route, 'prices': prices, 'estimate': estimate, 'acceptedAt': now}

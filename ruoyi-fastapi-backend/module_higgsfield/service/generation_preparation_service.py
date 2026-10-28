"""受理和预检共享固定输入、路由、价格及预估，事务由调用方管理。"""

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_estimate_service import GenerationEstimateService
from module_higgsfield.service.generation_input_service import GenerationInputService
from module_higgsfield.service.generation_policy_service import GenerationPolicyService
from module_higgsfield.service.generation_price_service import GenerationPriceService
from module_higgsfield.service.generation_route_service import GenerationRouteService
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.project_workspace_service import WorkspaceService


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
        capabilities = await ModelCatalogService.selected(
            db, user, int(payload.project_id), int(payload.model_version_id), payload.kind
        )
        try:
            estimate = GenerationEstimateService.calculate(
                capabilities,
                model_version_id=payload.model_version_id,
                input_snapshot=prepared['inputSnapshot'],
                prices=prices,
            )
        except ValueError:
            WorkspaceService.conflict('GENERATION_ESTIMATE_UNAVAILABLE', '预估策略与当前价格不兼容，请联系管理员核查')
        if payload.estimate_token:
            (tokens or GenerationPolicyService.tokens()).verify(
                payload.estimate_token,
                actor_id=user.user.user_id,
                payload=payload,
                prices=prices,
                estimate=estimate,
                now=now,
            )
        return {**prepared, 'route': route, 'prices': prices, 'estimate': estimate, 'acceptedAt': now}

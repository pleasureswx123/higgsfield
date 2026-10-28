"""预检只检查可受理性与签发估价，不创建任务或预占额度。"""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceWarning
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.budget_reservation_service import BudgetReservationService
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_preparation_service import GenerationPreparationService
from module_higgsfield.service.price_calculation_service import decimal_value
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationValidationService:
    @staticmethod
    async def validate(
        db: AsyncSession,
        user: CurrentUserModel,
        payload: GenerationInput,
        policy: GenerationPolicy,
        tokens: EstimateTokenService,
    ) -> dict:
        # 授权失败仍使用框架错误，不当作可供越权探测的业务问题返回。
        _, _, allowed = await WorkspaceService.authorize(db, user, int(payload.project_id), 'generation:create')
        try:
            prepared = await GenerationPreparationService.prepare(
                db, user, payload.model_copy(update={'estimate_token': None}), currencies=policy.currencies()
            )
            amounts = {
                (purpose, value['currency']): decimal_value(value['total'], 24, 10)
                for purpose, value in prepared['estimate']['estimates'].items()
            }
            await BudgetReservationService.plan(
                db,
                user,
                project_id=int(payload.project_id),
                at=prepared['acceptedAt'],
                amounts=amounts,
                missing_budget_policy=policy.missing_budget_policy,
            )
            token = tokens.issue(
                actor_id=user.user.user_id,
                payload=payload,
                prices=prepared['prices'],
                estimate=prepared['estimate'],
                now=prepared['acceptedAt'],
            )
            visible = 'project:usage:read' in allowed
            result = {
                'valid': True,
                'issues': [],
                'normalizedParameters': prepared['inputSnapshot']['parameters'],
                'estimateVisibility': 'visible' if visible else 'hidden',
                'estimateToken': token,
                'expiresAt': prepared['acceptedAt'] + timedelta(seconds=300),
            }
            if visible:
                price = prepared['estimate']['estimates']['platform']
                result.update(
                    estimate={'amount': price['total'], 'currency': price['currency']},
                    priceVersionId=price['priceVersionId'],
                )
            return result
        except ServiceWarning as error:
            return {
                'valid': False,
                'issues': [
                    {
                        'field': '$',
                        'code': (error.data or {}).get('errorCode', 'GENERATION_NOT_READY'),
                        'message': error.message,
                    }
                ],
                'normalizedParameters': {},
                'estimateVisibility': 'hidden',
            }
        finally:
            await db.rollback()

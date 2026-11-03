"""只检查输入和接入配置，不估价、不签发报价、不创建任务或预占额度。"""


from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceWarning
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_preparation_service import GenerationPreparationService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationValidationService:
    @staticmethod
    async def validate(
        db: AsyncSession,
        user: CurrentUserModel,
        payload: GenerationInput,
        policy: GenerationPolicy,
        tokens: EstimateTokenService | None = None,
    ) -> dict:
        # 授权失败仍使用框架错误，不当作可供越权探测的业务问题返回。
        await WorkspaceService.authorize(db, user, int(payload.project_id), 'generation:create')
        try:
            prepared = await GenerationPreparationService.prepare(
                db, user, payload.model_copy(update={'estimate_token': None}), currencies=policy.currencies()
            )
            result = {
                'valid': True, 'issues': [],
                'normalizedParameters': prepared['inputSnapshot']['parameters'],
                'estimateVisibility': 'hidden',
            }
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

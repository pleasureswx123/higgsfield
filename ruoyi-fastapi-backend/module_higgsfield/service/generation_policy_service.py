"""首版按实际用量以USD记账；历史估价工具保留但不参与新任务。"""

from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationPolicyService:
    @staticmethod
    def configured() -> GenerationPolicy:
        # 已确认的首版统一美元计价，不再依赖预算或估价环境变量。
        return GenerationPolicy(platform_currency='USD', procurement_currency='USD', missing_budget_policy='allow')

    @staticmethod
    def tokens() -> EstimateTokenService:
        try:
            return EstimateTokenService.from_environment()
        except ValueError:
            WorkspaceService.conflict('GENERATION_POLICY_UNAVAILABLE', '估价签名服务尚未有效配置')
        raise AssertionError('签名配置错误必须中止')

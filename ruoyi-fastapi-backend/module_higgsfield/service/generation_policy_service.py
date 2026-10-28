"""运行时业务策略和估价密钥缺失时明确拒绝生成入口。"""

import os

from pydantic import ValidationError

from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationPolicyService:
    @staticmethod
    def configured() -> GenerationPolicy:
        try:
            return GenerationPolicy.model_validate_json(os.environ['HF_GENERATION_POLICY'])
        except (KeyError, ValidationError):
            WorkspaceService.conflict('GENERATION_POLICY_UNAVAILABLE', '生成业务策略尚未有效配置')
        raise AssertionError('策略错误必须中止')

    @staticmethod
    def tokens() -> EstimateTokenService:
        try:
            return EstimateTokenService.from_environment()
        except ValueError:
            WorkspaceService.conflict('GENERATION_POLICY_UNAVAILABLE', '估价签名服务尚未有效配置')
        raise AssertionError('签名配置错误必须中止')

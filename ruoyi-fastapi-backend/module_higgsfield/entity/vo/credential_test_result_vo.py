"""测试诊断仅允许固定事实，不接受原始响应、URL或自由文本错误。"""
from typing import Literal
from pydantic import Field, StrictBool, StrictInt, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput


class CredentialTestResult(WorkspaceInput):
    transport: Literal['not_sent', 'response', 'timeout', 'network_error']
    authentication: Literal['passed', 'failed', 'unknown']
    acceptance: Literal['accepted', 'rejected', 'unknown', 'not_applicable']
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    model_verified: StrictBool = False
    output_count: StrictInt = Field(default=0, ge=0, le=1000)
    issue: Literal['NONE', 'CONFIG_CHANGED', 'CREDENTIAL_UNAVAILABLE', 'COST_CENTER_UNAVAILABLE',
                   'MODEL_UNAVAILABLE', 'PROBE_UNSUPPORTED', 'AUTH_REJECTED', 'PROVIDER_REJECTED',
                   'TRANSPORT_UNKNOWN', 'RESPONSE_INVALID', 'EXECUTION_INTERRUPTED']

    @model_validator(mode='after')
    def consistent(self):
        if (self.transport == 'response') != (self.http_status is not None):
            raise ValueError('仅真实响应可以携带HTTP状态')
        if self.transport != 'response':
            if self.authentication != 'unknown' or self.model_verified or self.output_count:
                raise ValueError('未收到响应不能证明鉴权或模型通过')
            expected = 'not_applicable' if self.transport == 'not_sent' else 'unknown'
            if self.acceptance != expected:
                raise ValueError('未发送和传输未知必须保留不同受理事实')
        if self.authentication == 'failed' and self.http_status not in {401, 403}:
            raise ValueError('鉴权失败必须有明确拒绝状态')
        if self.authentication == 'failed' and (self.acceptance != 'rejected' or self.issue != 'AUTH_REJECTED'):
            raise ValueError('鉴权拒绝必须保留拒绝事实')
        if self.issue == 'AUTH_REJECTED' and self.authentication != 'failed':
            raise ValueError('鉴权拒绝诊断必须有鉴权失败事实')
        if self.authentication == 'passed' and not (200 <= self.http_status < 300 and self.acceptance == 'accepted'):
            raise ValueError('鉴权通过需要成功响应及已受理事实')
        if self.model_verified and not (self.authentication == 'passed' and self.output_count > 0 and self.issue == 'NONE'):
            raise ValueError('模型通过需要有效结果证据')
        if self.issue == 'NONE' and not self.model_verified:
            raise ValueError('没有有效模型结果不能宣称测试无问题')
        return self

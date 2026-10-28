"""凭据写入输入；秘密不参与模型表示或常规序列化。"""

from datetime import timezone
from typing import Literal
from pydantic import AwareDatetime, ConfigDict, Field, SecretStr, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import BigId, WorkspaceInput


class CredentialSecretInput(WorkspaceInput):
    model_config = ConfigDict(hide_input_in_errors=True)

    connection_version_id: BigId
    api_key: SecretStr = Field(exclude=True, repr=False)
    valid_from: AwareDatetime
    valid_until: AwareDatetime | None = None

    @field_validator('api_key')
    @classmethod
    def secret_format(cls, value):
        secret = value.get_secret_value()
        if not 8 <= len(secret) <= 4096 or any(ord(char) < 33 or ord(char) > 126 for char in secret):
            raise ValueError('供应商密钥必须为8至4096个可打印ASCII字符，且不能包含空白')
        return value

    @field_validator('valid_from', 'valid_until')
    @classmethod
    def utc_time(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None

    @model_validator(mode='after')
    def validity(self):
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError('有效期结束时间必须晚于开始时间')
        return self


class CredentialCreate(CredentialSecretInput):
    account_id: BigId
    owner_id: BigId
    name: str = Field(min_length=1, max_length=200)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError('凭据名称不能为空或包含控制字符')
        return value.strip()


class CredentialVersionCreate(CredentialSecretInput):
    revision: BigId


class CredentialPage(WorkspaceInput):
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CredentialStateAction(WorkspaceInput):
    revision: BigId
    reason: str = Field(min_length=1, max_length=4000)

    @field_validator('reason')
    @classmethod
    def required_reason(cls, value):
        if not value.strip():
            raise ValueError('凭据状态操作必须填写原因')
        return value.strip()


class CredentialQuery(CredentialPage):
    account_id: BigId | None = None
    status: Literal['draft', 'active', 'draining', 'disabled', 'revoked'] | None = None


class CredentialActivate(CredentialStateAction):
    test_id: BigId
    expected_config_hash: str = Field(pattern=r'^[a-f0-9]{64}$')

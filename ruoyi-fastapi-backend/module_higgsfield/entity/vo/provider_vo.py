"""连接登记只接受白名单配置，不接受密钥或任意请求头。"""

import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit
from pydantic import Field, StrictInt, field_validator, model_validator
from module_higgsfield.entity.vo.project_workspace_vo import WorkspaceInput, BigId


def domain(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', value):
        raise ValueError('允许域名必须为完整ASCII主机名，不使用通配符或端口')
    if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-') for label in value.split('.')):
        raise ValueError('允许域名格式无效')
    return value


class ConnectionConfig(WorkspaceInput):
    allowed_hosts: list[str] = Field(min_length=1, max_length=30)
    biz_id: Literal['op'] = 'op'
    connect_timeout_seconds: StrictInt = Field(ge=1, le=120)
    read_timeout_seconds: StrictInt = Field(ge=1, le=3600)
    operation_timeout_seconds: StrictInt = Field(ge=1, le=3600)
    task_timeout_seconds: StrictInt = Field(ge=1, le=604800)

    @field_validator('allowed_hosts')
    @classmethod
    def hosts(cls, values):
        result = [domain(value) for value in values]
        if len(set(result)) != len(result):
            raise ValueError('允许域名不能重复')
        return sorted(result)

    @model_validator(mode='after')
    def timeouts(self):
        if (
            self.operation_timeout_seconds < max(self.connect_timeout_seconds, self.read_timeout_seconds)
            or self.task_timeout_seconds < self.operation_timeout_seconds
        ):
            raise ValueError('操作超时不得短于连接/读取超时，任务超时不得短于操作超时')
        return self


class ConnectionFields(WorkspaceInput):
    name: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=2000)
    adapter_version: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
    config: ConnectionConfig

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError('连接名称不能为空或包含控制字符')
        return value.strip()

    @field_validator('base_url')
    @classmethod
    def safe_url(cls, value):
        if any(ord(c) < 33 or ord(c) > 126 for c in value) or '\\' in value or '%' in value:
            raise ValueError('连接地址必须使用不含控制字符和转义的ASCII地址')
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ('http', 'https')
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError('连接地址只允许HTTP/HTTPS主机和路径，不携带凭据、查询或片段')
        host = domain(parsed.hostname)
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError('连接端口无效')
        if any(part in ('.', '..') for part in parsed.path.split('/')):
            raise ValueError('连接地址不能含路径跳转')
        authority = host + (f':{port}' if port else '')
        return urlunsplit((parsed.scheme, authority, parsed.path.rstrip('/') + '/', '', ''))

    @model_validator(mode='after')
    def host_allowed(self):
        if urlsplit(self.base_url).hostname not in self.config.allowed_hosts:
            raise ValueError('连接主机必须显式列入允许域名')
        return self


class ConnectionCreate(ConnectionFields):
    environment: Literal['test', 'production']


class ConnectionPatch(WorkspaceInput):
    revision: BigId
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=1, max_length=2000)
    adapter_version: str | None = Field(default=None, min_length=1, max_length=100)
    config: ConnectionConfig | None = None

    @model_validator(mode='after')
    def nonempty(self):
        fields = self.model_fields_set - {'revision'}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError('连接更新必须提供非空修改字段')
        return self


class ConnectionQuery(WorkspaceInput):
    environment: Literal['test', 'production'] | None = None
    status: Literal['draft', 'active', 'disabled'] | None = None
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)


class ProviderAccountCreate(WorkspaceInput):
    connection_id: BigId
    account_code: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=32, pattern=r'^[a-z][a-z0-9_-]*$')
    upstream_project: str = Field(min_length=1, max_length=100)

    @field_validator('account_code', 'upstream_project')
    @classmethod
    def exact_identifier(cls, value):
        if value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError('账号及上游项目标识不得包含首尾空白或控制字符')
        return value


class ProviderAccountQuery(WorkspaceInput):
    account_id: BigId | None = None
    connection_id: BigId | None = None
    region: str | None = Field(default=None, max_length=32, pattern=r'^[a-z][a-z0-9_-]*$')
    page_num: int = Field(default=1, ge=1)
    page_size: int = Field(default=30, ge=1, le=100)

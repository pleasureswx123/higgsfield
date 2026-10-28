from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from common.mixin import AuditTimeMixin
from config.database import Base


class HfProject(AuditTimeMixin, Base):
    """项目。"""

    __tablename__ = 'hf_project'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        CheckConstraint("status IN ('0','1','2','3')", name='ck_hf_project_status'),
        CheckConstraint("del_flag IN ('0','2')", name='ck_hf_project_del'),
        CheckConstraint("status != '2' OR archived_time IS NOT NULL", name='ck_hf_project_archived'),
        CheckConstraint('revision > 0', name='ck_hf_project_revision'),
        Index('ix_hf_project_status_time', 'status', 'create_time', 'project_id'),
        {'comment': '项目', 'info': {'migration_managed': True}},
    )
    project_id = Column(
        'project_id', BigInteger, nullable=False, comment='项目ID', primary_key=True, autoincrement=True
    )
    project_name = Column('project_name', String(200), nullable=False, comment='项目名称')
    status = Column(
        'status', CHAR(1), nullable=False, comment='状态：0进行中1暂停2归档3待删除', server_default=text("'0'")
    )
    create_user_id = Column('create_user_id', BigInteger, nullable=False, comment='创建用户ID')
    revision = Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1'))
    archived_time = Column('archived_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='归档时间')
    del_flag = Column('del_flag', CHAR(1), nullable=False, comment='删除标志：0存在2删除', server_default=text("'0'"))
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfProjectRole(AuditTimeMixin, Base):
    """项目角色。"""

    __tablename__ = 'hf_project_role'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint('code', name='uq_hf_project_role_code'),
        CheckConstraint("is_system IN ('Y','N')", name='ck_hf_project_role_system'),
        {'comment': '项目角色', 'info': {'migration_managed': True}},
    )
    role_id = Column('role_id', BigInteger, nullable=False, comment='角色ID', primary_key=True, autoincrement=True)
    code = Column('code', String(100), nullable=False, comment='稳定角色编码')
    role_name = Column('role_name', String(200), nullable=False, comment='角色名称')
    is_system = Column('is_system', CHAR(1), nullable=False, comment='是否系统角色：Y是N否', server_default=text("'Y'"))
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfProjectMember(AuditTimeMixin, Base):
    """项目成员。"""

    __tablename__ = 'hf_project_member'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint('project_id', 'user_id', name='uq_hf_project_member'),
        CheckConstraint("status IN ('0','1')", name='ck_hf_member_status'),
        CheckConstraint('revision > 0', name='ck_hf_member_revision'),
        Index('ix_hf_member_user_status', 'user_id', 'status', 'project_id'),
        {'comment': '项目成员', 'info': {'migration_managed': True}},
    )
    member_id = Column('member_id', BigInteger, nullable=False, comment='成员ID', primary_key=True, autoincrement=True)
    project_id = Column('project_id', BigInteger, nullable=False, comment='项目ID')
    user_id = Column('user_id', BigInteger, nullable=False, comment='用户ID')
    role_id = Column('role_id', BigInteger, nullable=False, comment='角色ID')
    status = Column('status', CHAR(1), nullable=False, comment='状态：0有效1已移除', server_default=text("'0'"))
    joined_time = Column('joined_time', TIMESTAMP(timezone=True, precision=3), nullable=False, comment='加入时间')
    removed_time = Column('removed_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='移除时间')
    revision = Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1'))
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfProjectRolePermission(AuditTimeMixin, Base):
    """项目角色权限。"""

    __tablename__ = 'hf_project_role_permission'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint('role_id', 'permission_code', name='uq_hf_project_role_permission'),
        CheckConstraint("data_scope IN ('own','project')", name='ck_hf_role_scope'),
        {'comment': '项目角色权限', 'info': {'migration_managed': True}},
    )
    role_permission_id = Column(
        'role_permission_id', BigInteger, nullable=False, comment='角色权限ID', primary_key=True, autoincrement=True
    )
    role_id = Column('role_id', BigInteger, nullable=False, comment='角色ID')
    permission_code = Column('permission_code', String(100), nullable=False, comment='操作权限码')
    data_scope = Column('data_scope', String(32), nullable=False, comment='数据范围：own本人project项目')
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfAssetSpace(AuditTimeMixin, Base):
    """内容归属空间。"""

    __tablename__ = 'hf_asset_space'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        CheckConstraint(
            "(kind='project' AND project_id IS NOT NULL) OR (kind='public' AND project_id IS NULL)",
            name='ck_hf_asset_space_kind',
        ),
        Index('uq_hf_asset_space_project', 'project_id', unique=True, postgresql_where=text('project_id IS NOT NULL')),
        {'comment': '内容归属空间', 'info': {'migration_managed': True}},
    )
    space_id = Column('space_id', BigInteger, nullable=False, comment='空间ID', primary_key=True, autoincrement=True)
    kind = Column('kind', String(32), nullable=False, comment='空间类型：project项目public公共')
    project_id = Column('project_id', BigInteger, nullable=True, comment='所属项目ID')
    space_name = Column('space_name', String(200), nullable=False, comment='空间名称')
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfProjectBrief(AuditTimeMixin, Base):
    """项目简报。"""

    __tablename__ = 'hf_project_brief'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint('project_id', name='uq_hf_project_brief'),
        CheckConstraint("jsonb_typeof(body) = 'object'", name='ck_hf_brief_body'),
        CheckConstraint('revision > 0', name='ck_hf_brief_revision'),
        {'comment': '项目简报', 'info': {'migration_managed': True}},
    )
    brief_id = Column('brief_id', BigInteger, nullable=False, comment='简报ID', primary_key=True, autoincrement=True)
    project_id = Column('project_id', BigInteger, nullable=False, comment='项目ID')
    body = Column('body', JSONB, nullable=False, comment='白名单富文本正文', server_default=text("'{}'::jsonb"))
    schema_version = Column('schema_version', Integer, nullable=False, comment='格式版本', server_default=text('1'))
    revision = Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1'))
    update_user_id = Column('update_user_id', BigInteger, nullable=False, comment='编辑用户ID')
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))


class HfApiIdempotencyRecord(AuditTimeMixin, Base):
    """写请求幂等记录。"""

    __tablename__ = 'hf_api_idempotency_record'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint(
            'actor_id',
            'api_prefix',
            'http_method',
            'normalized_path',
            'idempotency_key',
            name='uq_hf_api_idempotency_scope',
        ),
        CheckConstraint("idempotency_key ~ '^[ -~]{16,128}$'", name='ck_hf_idempotency_key'),
        CheckConstraint("state IN ('0','1','2')", name='ck_hf_idempotency_state'),
        CheckConstraint(
            "state != '1' OR (http_status IS NOT NULL AND completed_time IS NOT NULL AND safe_result IS NOT NULL)",
            name='ck_hf_idempotency_complete',
        ),
        CheckConstraint('http_status BETWEEN 100 AND 599', name='ck_hf_idempotency_http'),
        CheckConstraint('fencing_token >= 0', name='ck_hf_idempotency_fence'),
        CheckConstraint('expires_time > create_time', name='ck_hf_idempotency_expiry'),
        Index('ix_hf_idempotency_expiry', 'state', 'expires_time'),
        Index('ix_hf_idempotency_lease', 'state', 'lease_until'),
        {'comment': '写请求幂等记录', 'info': {'migration_managed': True}},
    )
    record_id = Column(
        'record_id', BigInteger, nullable=False, comment='幂等记录ID', primary_key=True, autoincrement=True
    )
    actor_id = Column('actor_id', BigInteger, nullable=False, comment='操作用户ID')
    api_prefix = Column('api_prefix', String(100), nullable=False, comment='接口前缀')
    http_method = Column('http_method', String(10), nullable=False, comment='请求方法')
    normalized_path = Column('normalized_path', String(512), nullable=False, comment='规范请求路径')
    idempotency_key = Column('idempotency_key', String(128), nullable=False, comment='幂等键')
    request_hash = Column('request_hash', CHAR(64), nullable=False, comment='规范请求摘要')
    hash_key_version = Column('hash_key_version', String(100), nullable=True, comment='摘要密钥版本')
    state = Column('state', CHAR(1), nullable=False, comment='状态：0处理中1完成2待恢复')
    http_status = Column('http_status', SmallInteger, nullable=True, comment='原HTTP状态码')
    result_type = Column('result_type', String(100), nullable=True, comment='结果类型')
    result_id = Column('result_id', Text, nullable=True, comment='结果资源ID')
    safe_result = Column('safe_result', JSONB, nullable=True, comment='脱敏原始响应')
    schema_version = Column('schema_version', Integer, nullable=False, comment='投影版本', server_default=text('1'))
    expires_time = Column('expires_time', TIMESTAMP(timezone=True, precision=3), nullable=False, comment='保留截止时间')
    lease_until = Column('lease_until', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='处理租约截止')
    fencing_token = Column('fencing_token', BigInteger, nullable=False, comment='执行栅栏', server_default=text('0'))
    completed_time = Column('completed_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='完成时间')
    create_by = Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''"))
    update_by = Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''"))

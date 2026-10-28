"""初始化制作平台项目基础表、角色、权限与幂等记录。"""

from alembic import op
from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision = '20261027_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """创建项目最小业务闭环；保留已有框架数据。"""
    op.create_table(
        'hf_project',
        Column('project_id', BigInteger, nullable=False, comment='项目ID', primary_key=True, autoincrement=True),
        Column('project_name', String(200), nullable=False, comment='项目名称'),
        Column('status', CHAR(1), nullable=False, comment='状态：0进行中1暂停2归档3待删除', server_default=text("'0'")),
        Column('create_user_id', BigInteger, nullable=False, comment='创建用户ID'),
        Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1')),
        Column('archived_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='归档时间'),
        Column('del_flag', CHAR(1), nullable=False, comment='删除标志：0存在2删除', server_default=text("'0'")),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        CheckConstraint("status IN ('0','1','2','3')", name='ck_hf_project_status'),
        CheckConstraint("del_flag IN ('0','2')", name='ck_hf_project_del'),
        CheckConstraint("status != '2' OR archived_time IS NOT NULL", name='ck_hf_project_archived'),
        CheckConstraint('revision > 0', name='ck_hf_project_revision'),
        comment='项目',
    )
    op.create_index('ix_hf_project_status_time', 'hf_project', ['status', 'create_time', 'project_id'])
    op.create_table(
        'hf_project_role',
        Column('role_id', BigInteger, nullable=False, comment='角色ID', primary_key=True, autoincrement=True),
        Column('code', String(100), nullable=False, comment='稳定角色编码'),
        Column('role_name', String(200), nullable=False, comment='角色名称'),
        Column('is_system', CHAR(1), nullable=False, comment='是否系统角色：Y是N否', server_default=text("'Y'")),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        UniqueConstraint('code', name='uq_hf_project_role_code'),
        CheckConstraint("is_system IN ('Y','N')", name='ck_hf_project_role_system'),
        comment='项目角色',
    )
    op.create_table(
        'hf_project_member',
        Column('member_id', BigInteger, nullable=False, comment='成员ID', primary_key=True, autoincrement=True),
        Column('project_id', BigInteger, nullable=False, comment='项目ID'),
        Column('user_id', BigInteger, nullable=False, comment='用户ID'),
        Column('role_id', BigInteger, nullable=False, comment='角色ID'),
        Column('status', CHAR(1), nullable=False, comment='状态：0有效1已移除', server_default=text("'0'")),
        Column('joined_time', TIMESTAMP(timezone=True, precision=3), nullable=False, comment='加入时间'),
        Column('removed_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='移除时间'),
        Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1')),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        UniqueConstraint('project_id', 'user_id', name='uq_hf_project_member'),
        CheckConstraint("status IN ('0','1')", name='ck_hf_member_status'),
        CheckConstraint('revision > 0', name='ck_hf_member_revision'),
        comment='项目成员',
    )
    op.create_index('ix_hf_member_user_status', 'hf_project_member', ['user_id', 'status', 'project_id'])
    op.create_table(
        'hf_project_role_permission',
        Column(
            'role_permission_id', BigInteger, nullable=False, comment='角色权限ID', primary_key=True, autoincrement=True
        ),
        Column('role_id', BigInteger, nullable=False, comment='角色ID'),
        Column('permission_code', String(100), nullable=False, comment='操作权限码'),
        Column('data_scope', String(32), nullable=False, comment='数据范围：own本人project项目'),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        UniqueConstraint('role_id', 'permission_code', name='uq_hf_project_role_permission'),
        CheckConstraint("data_scope IN ('own','project')", name='ck_hf_role_scope'),
        comment='项目角色权限',
    )
    op.create_table(
        'hf_asset_space',
        Column('space_id', BigInteger, nullable=False, comment='空间ID', primary_key=True, autoincrement=True),
        Column('kind', String(32), nullable=False, comment='空间类型：project项目public公共'),
        Column('project_id', BigInteger, nullable=True, comment='所属项目ID'),
        Column('space_name', String(200), nullable=False, comment='空间名称'),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        CheckConstraint(
            "(kind='project' AND project_id IS NOT NULL) OR (kind='public' AND project_id IS NULL)",
            name='ck_hf_asset_space_kind',
        ),
        comment='内容归属空间',
    )
    op.create_index(
        'uq_hf_asset_space_project',
        'hf_asset_space',
        ['project_id'],
        unique=True,
        postgresql_where=text('project_id IS NOT NULL'),
    )
    op.create_table(
        'hf_project_brief',
        Column('brief_id', BigInteger, nullable=False, comment='简报ID', primary_key=True, autoincrement=True),
        Column('project_id', BigInteger, nullable=False, comment='项目ID'),
        Column('body', JSONB, nullable=False, comment='白名单富文本正文', server_default=text("'{}'::jsonb")),
        Column('schema_version', Integer, nullable=False, comment='格式版本', server_default=text('1')),
        Column('revision', BigInteger, nullable=False, comment='并发版本', server_default=text('1')),
        Column('update_user_id', BigInteger, nullable=False, comment='编辑用户ID'),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        UniqueConstraint('project_id', name='uq_hf_project_brief'),
        CheckConstraint("jsonb_typeof(body) = 'object'", name='ck_hf_brief_body'),
        comment='项目简报',
    )
    op.create_table(
        'hf_api_idempotency_record',
        Column('record_id', BigInteger, nullable=False, comment='幂等记录ID', primary_key=True, autoincrement=True),
        Column('actor_id', BigInteger, nullable=False, comment='操作用户ID'),
        Column('api_prefix', String(100), nullable=False, comment='接口前缀'),
        Column('http_method', String(10), nullable=False, comment='请求方法'),
        Column('normalized_path', String(512), nullable=False, comment='规范请求路径'),
        Column('idempotency_key', String(128), nullable=False, comment='幂等键'),
        Column('request_hash', CHAR(64), nullable=False, comment='规范请求摘要'),
        Column('hash_key_version', String(100), nullable=True, comment='摘要密钥版本'),
        Column('state', CHAR(1), nullable=False, comment='状态：0处理中1完成2待恢复'),
        Column('http_status', SmallInteger, nullable=True, comment='原HTTP状态码'),
        Column('result_type', String(100), nullable=True, comment='结果类型'),
        Column('result_id', Text, nullable=True, comment='结果资源ID'),
        Column('safe_result', JSONB, nullable=True, comment='脱敏原始响应'),
        Column('schema_version', Integer, nullable=False, comment='投影版本', server_default=text('1')),
        Column('expires_time', TIMESTAMP(timezone=True, precision=3), nullable=False, comment='保留截止时间'),
        Column('lease_until', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='处理租约截止'),
        Column('fencing_token', BigInteger, nullable=False, comment='执行栅栏', server_default=text('0')),
        Column('completed_time', TIMESTAMP(timezone=True, precision=3), nullable=True, comment='完成时间'),
        Column('create_by', String(64), nullable=False, comment='创建者', server_default=text("''")),
        Column('update_by', String(64), nullable=False, comment='更新者', server_default=text("''")),
        Column(
            'create_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='创建时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
        Column(
            'update_time',
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            comment='更新时间',
            server_default=text('CURRENT_TIMESTAMP'),
        ),
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
        comment='写请求幂等记录',
    )
    op.create_index('ix_hf_idempotency_expiry', 'hf_api_idempotency_record', ['state', 'expires_time'])
    op.create_index('ix_hf_idempotency_lease', 'hf_api_idempotency_record', ['state', 'lease_until'])
    op.execute(
        "INSERT INTO hf_project_role (code, role_name) VALUES ('owner','负责人'), ('producer','制作人'), ('viewer','查看者')"
    )
    op.execute(
        "INSERT INTO hf_project_role_permission (role_id, permission_code, data_scope) SELECT role_id, 'project:read', 'project' FROM hf_project_role"
    )
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '制作平台项目权限',0,50,'studio-project-permissions','M','1','0','', 'migration_hf_01',CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE path='studio-project-permissions')"
    )
    for label, permission in [('查看项目', 'project:read'), ('创建项目', 'project:create')]:
        op.execute(
            text(
                "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT :label,menu_id,1,'','F','1','0',:permission,'migration_hf_01',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)"
            ).bindparams(label=label, permission=permission)
        )


def downgrade():
    """业务数据不自动删除，回退需要单独审核迁移。"""
    raise RuntimeError('项目迁移包含用户业务数据，不支持自动删除回退')

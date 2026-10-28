"""补齐内置项目负责人组织素材与创作的基础能力，不授予供应商及财务管理权限。"""
from alembic import op
from sqlalchemy import text

revision = '20261028_77'
down_revision = '20261028_76'
branch_labels = None
depends_on = None


def upgrade():
    # 仅补齐内置负责人；制作人、查看者及自定义角色仍由管理员配置。
    for permission in (
        'asset:read', 'folder:write', 'asset:upload', 'asset:create',
        'element:read', 'element:create', 'element:edit', 'generation:create',
    ):
        op.execute(text("""INSERT INTO hf_project_role_permission
            (role_id,permission_code,data_scope,create_by,update_by,create_time,update_time)
            SELECT role_id,:permission,'project','migration_hf_77','migration_hf_77',
                CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
            FROM hf_project_role WHERE code='owner' AND is_system='Y'
            ON CONFLICT(role_id,permission_code) DO NOTHING""").bindparams(permission=permission))


def downgrade():
    raise RuntimeError('业务角色权限回退需单独审核，不自动删除授权')

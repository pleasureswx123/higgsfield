"""补齐项目负责人将项目素材用于创作引用的权限。"""
from alembic import op

revision = '20261028_78'
down_revision = '20261028_77'
branch_labels = None
depends_on = None


def upgrade():
    # 引用与读取是独立权限；只补齐内置负责人，不扩大其他角色或下载权限。
    op.execute("""INSERT INTO hf_project_role_permission
        (role_id,permission_code,data_scope,create_by,update_by,create_time,update_time)
        SELECT role_id,'asset:reference','project','migration_hf_78','migration_hf_78',
            CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
        FROM hf_project_role WHERE code='owner' AND is_system='Y'
        ON CONFLICT(role_id,permission_code) DO NOTHING""")


def downgrade():
    raise RuntimeError('业务角色权限回退需单独审核，不自动删除授权')

"""登记凭据启用权限，不自动授予角色。"""
from alembic import op
revision = '20261028_60'
down_revision = '20261028_59'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '启用供应商凭据',menu_id,35,'','F','1','0','credential:activate','migration_hf_60',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='credential:activate')""")


def downgrade():
    raise RuntimeError('权限可能已有授权，请通过经审核的权限迁移处理')

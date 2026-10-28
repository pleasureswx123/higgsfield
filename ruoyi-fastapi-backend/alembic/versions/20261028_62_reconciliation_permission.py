"""登记对账操作权限，不自动授予角色。"""
from alembic import op
revision = '20261028_62'
down_revision = '20261028_61'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '导入与确认供应商账单',menu_id,36,'','F','1','0','billing:reconcile','migration_hf_62',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='billing:reconcile')""")


def downgrade():
    raise RuntimeError('对账权限可能已有授权，请通过经审核的权限迁移处理')

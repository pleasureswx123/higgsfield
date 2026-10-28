"""登记运行治理只读权限，不自动授予角色。"""
from alembic import op
revision = '20261028_52'
down_revision = '20261028_51'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '运行治理查询',menu_id,32,'','F','1','0','operations:read','migration_hf_52',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:read')""")


def downgrade():
    raise RuntimeError('运行治理权限不能自动回退删除')

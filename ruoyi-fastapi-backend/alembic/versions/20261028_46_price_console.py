"""价格管理管理入口，不自动授予角色权限。"""
from alembic import op

revision = '20261028_46'
down_revision = '20261028_45'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '价格管理',menu_id,7,'prices','studio/prices/index','C','0','0',
        'billing:price:read','tree','migration_hf_46',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/prices/index')""")


def downgrade():
    raise RuntimeError('价格入口与授权需人工审核，不自动删除')

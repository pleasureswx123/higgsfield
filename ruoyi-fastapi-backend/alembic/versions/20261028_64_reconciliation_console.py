"""注册对账页面，不自动授予角色权限。"""
from alembic import op
revision = '20261028_64'
down_revision = '20261028_63'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '供应商账单对账',menu_id,12,'reconciliations','studio/reconciliations/index','C','0','0',
        'billing:read','list','migration_hf_64',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/reconciliations/index')""")


def downgrade():
    raise RuntimeError('对账入口与角色授权须经审核，不自动删除')

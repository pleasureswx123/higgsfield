"""注册供应商调用页面，不自动授予角色权限。"""
from alembic import op
revision = '20261028_53'
down_revision = '20261028_52'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '供应商调用',menu_id,10,'calls','studio/calls/index','C','0','0',
        'operations:read','list','migration_hf_53',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/calls/index')""")


def downgrade():
    raise RuntimeError('调用入口与授权需人工审核，不自动删除')

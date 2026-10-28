"""供应商连接与账号管理页面入口，不自动授予角色权限。"""

from alembic import op

revision = '20261027_20'
down_revision = '20261027_19'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '供应商连接',menu_id,2,'provider-connections','studio/providers/index','C','0','0',
        'provider:read','link','migration_hf_20',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/providers/index')""")


def downgrade():
    raise RuntimeError('页面入口与授权需人工审核，不自动删除')

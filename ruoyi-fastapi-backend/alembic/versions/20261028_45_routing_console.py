"""项目模型路由管理入口，不自动授予角色权限。"""
from alembic import op

revision = '20261028_45'
down_revision = '20261028_44'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '项目模型路由',menu_id,6,'routing','studio/routing/index','C','0','0',
        'provider:route','tree','migration_hf_45',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/routing/index')""")


def downgrade():
    raise RuntimeError('路由入口与授权需人工审核，不自动删除')

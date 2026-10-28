"""注册业务审计页面，不自动授予角色权限。"""
from alembic import op
revision = '20261028_51'
down_revision = '20261028_50'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '业务审计',menu_id,9,'audit','studio/audit/index','C','0','0',
        'audit:read','list','migration_hf_51',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/audit/index')""")


def downgrade():
    raise RuntimeError('审计入口与授权需人工审核，不自动删除')

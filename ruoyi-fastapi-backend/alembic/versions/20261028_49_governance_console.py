"""项目治理页面入口，不自动授予角色权限。"""
from alembic import op

revision = '20261028_49'
down_revision = '20261028_48'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '项目治理',menu_id,8,'governance','studio/governance/index','C','0','0',
        'project:govern','tree','migration_hf_49',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/governance/index')""")


def downgrade():
    raise RuntimeError('治理入口与授权需人工审核，不自动删除')

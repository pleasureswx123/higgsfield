"""注册项目治理功能，不自动授予系统角色。"""
from alembic import op
revision = '20261028_48'
down_revision = '20261028_47'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '项目治理',menu_id,30,'','F','1','0','project:govern','migration_hf_48',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='project:govern')""")


def downgrade():
    raise RuntimeError('治理权限不能自动回退删除')

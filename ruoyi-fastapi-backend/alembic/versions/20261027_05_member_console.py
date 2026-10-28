"""后台项目成员配置菜单；不自动给用户授予任何项目权限。"""

from alembic import op
from sqlalchemy import text

revision = '20261027_05'
down_revision = '20261027_04'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        text("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '制作平台',0,8,'studio','M','0','0','','migration_hf_05',CURRENT_TIMESTAMP
        WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE path='studio' AND parent_id=0)""")
    )
    op.execute(
        text("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,create_by,create_time)
        SELECT '项目成员',menu_id,1,'project-members','studio/projectMembers/index','C','0','0',
        'project:read','migration_hf_05',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/projectMembers/index')""")
    )


def downgrade():
    raise RuntimeError('菜单授权回退需单独审核迁移')

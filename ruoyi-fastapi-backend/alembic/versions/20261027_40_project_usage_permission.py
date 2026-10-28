"""登记制作端平台费用读取权限，不自动授予项目负责人或系统角色。"""

from alembic import op

revision = '20261027_40'
down_revision = '20261027_39'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '读取项目平台费用',menu_id,20,'','F','1','0','project:usage:read','migration_hf_40',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='project:usage:read')"
    )


def downgrade():
    raise RuntimeError('业务权限配置不可自动回退删除')

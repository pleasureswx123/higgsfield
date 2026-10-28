"""登记费用调整功能权限，不自动授予系统或项目角色。"""

from alembic import op

revision = '20261028_41'
down_revision = '20261027_40'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '调整费用',menu_id,21,'','F','1','0','billing:adjust','migration_hf_41',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='billing:adjust')"
    )


def downgrade():
    raise RuntimeError('费用权限不可自动回退删除')

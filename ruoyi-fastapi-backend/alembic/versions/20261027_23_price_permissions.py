"""登记价格读写权限，不自动授予角色。"""

from alembic import op

revision = '20261027_23'
down_revision = '20261027_22'
branch_labels = None
depends_on = None


def upgrade():
    for name, permission in [('查看价格', 'billing:price:read'), ('维护价格', 'billing:price:write')]:
        op.execute(
            f"INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '{name}',menu_id,15,'','F','1','0','{permission}','migration_hf_23',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='{permission}')"
        )


def downgrade():
    op.execute(
        "DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='migration_hf_23')"
    )
    op.execute("DELETE FROM sys_menu WHERE create_by='migration_hf_23'")

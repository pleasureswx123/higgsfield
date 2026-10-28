"""登记预算查看、调整和账本查看权限，不默认授予角色。"""

from alembic import op

revision = '20261027_28'
down_revision = '20261027_27'
branch_labels = None
depends_on = None


def upgrade():
    for name, permission in [
        ('查看预算', 'billing:budget:read'),
        ('维护预算', 'billing:budget'),
        ('查看费用账本', 'billing:read'),
    ]:
        op.execute(
            f"INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '{name}',menu_id,17,'','F','1','0','{permission}','migration_hf_28',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='{permission}')"
        )


def downgrade():
    op.execute(
        "DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='migration_hf_28')"
    )
    op.execute("DELETE FROM sys_menu WHERE create_by='migration_hf_28'")

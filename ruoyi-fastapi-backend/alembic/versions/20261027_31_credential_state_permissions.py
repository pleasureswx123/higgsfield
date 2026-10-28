"""登记凭据排空停用及紧急撤销权限。"""

from alembic import op

revision = '20261027_31'
down_revision = '20261027_30'
branch_labels = None
depends_on = None


def upgrade():
    for name, permission in [('排空停用凭据', 'credential:disable'), ('紧急撤销凭据', 'credential:revoke')]:
        op.execute(
            f"INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '{name}',menu_id,18,'','F','1','0','{permission}','migration_hf_31',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='{permission}')"
        )


def downgrade():
    op.execute(
        "DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='migration_hf_31')"
    )
    op.execute("DELETE FROM sys_menu WHERE create_by='migration_hf_31'")

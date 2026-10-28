"""注册凭据读取、登记与轮换权限，不自动给角色授权。"""

from alembic import op

revision = '20261027_18'
down_revision = '20261027_17'
branch_labels = None
depends_on = None


def upgrade():
    for label, permission in (
        ('读取供应商凭据', 'credential:read'),
        ('登记供应商凭据', 'credential:write'),
        ('轮换供应商凭据', 'credential:rotate'),
    ):
        op.execute(
            'INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) '
            f"SELECT '{label}',menu_id,13,'','F','1','0','{permission}','migration_hf_18',CURRENT_TIMESTAMP "
            "FROM sys_menu WHERE path='studio-project-permissions' "
            f"AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='{permission}')"
        )


def downgrade():
    raise RuntimeError('凭据权限迁移不自动删除授权记录')

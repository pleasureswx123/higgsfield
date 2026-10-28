"""登记凭据测试权限，不自动授予角色。"""
from alembic import op
revision = '20261028_58'
down_revision = '20261028_57'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '测试供应商凭据',menu_id,34,'','F','1','0','credential:test','migration_hf_58',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='credential:test')""")


def downgrade():
    raise RuntimeError('凭据测试权限不自动回退删除')

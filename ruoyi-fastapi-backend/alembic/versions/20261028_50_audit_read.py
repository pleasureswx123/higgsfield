"""登记只读业务审计权限，不自动授予角色。"""
from alembic import op
revision = '20261028_50'
down_revision = '20261028_49'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '业务审计查询',menu_id,31,'','F','1','0','audit:read','migration_hf_50',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='audit:read')""")


def downgrade():
    raise RuntimeError('审计权限不能自动回退删除')

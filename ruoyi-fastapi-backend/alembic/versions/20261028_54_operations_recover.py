"""登记异常恢复权限，不自动授予角色。"""
from alembic import op
revision = '20261028_54'
down_revision = '20261028_53'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '异常任务恢复',menu_id,33,'','F','1','0','operations:recover','migration_hf_54',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='operations:recover')""")


def downgrade():
    raise RuntimeError('异常恢复权限不能自动回退删除')

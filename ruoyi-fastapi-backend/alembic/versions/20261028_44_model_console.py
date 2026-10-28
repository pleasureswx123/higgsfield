"""模型能力管理页面入口，不自动授予角色权限。"""
from alembic import op

revision = '20261028_44'
down_revision = '20261028_43'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '模型能力',menu_id,5,'models','studio/models/index','C','0','0',
        'model:read','component','migration_hf_44',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/models/index')""")


def downgrade():
    raise RuntimeError('模型入口与授权需人工审核，不自动删除')

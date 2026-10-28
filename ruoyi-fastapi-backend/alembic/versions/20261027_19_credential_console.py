"""凭据管理页面入口，沿用独立的读取与写入权限。"""

from alembic import op

revision = '20261027_19'
down_revision = '20261027_18'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,component,menu_type,visible,status,perms,icon,create_by,create_time)
        SELECT '供应商凭据',menu_id,3,'provider-credentials','studio/credentials/index','C','0','0',
        'credential:read','lock','migration_hf_19',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio' AND parent_id=0
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE component='studio/credentials/index')""")


def downgrade():
    raise RuntimeError('页面入口和角色授权需人工核查，不自动删除')

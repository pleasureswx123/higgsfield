"""登记生成创建功能码，默认角色授权仍由管理员明确配置。"""

from alembic import op

revision = '20261027_11'
down_revision = '20261027_10'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '创建项目生成',menu_id,9,'','F','1','0','generation:create','migration_hf_11',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='generation:create')"
    )


def downgrade():
    raise RuntimeError('业务权限配置不可自动回退删除')

"""登记生成读取功能权限；系统角色仍需管理员明确授权。"""

from alembic import op

revision = '20261027_32'
down_revision = '20261027_31'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '读取项目生成',menu_id,19,'','F','1','0','generation:read','migration_hf_32',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='generation:read')"
    )
    op.execute(
        "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'generation:read','project' FROM hf_project_role WHERE code IN ('owner','producer','viewer') ON CONFLICT(role_id,permission_code) DO NOTHING"
    )


def downgrade():
    raise RuntimeError('业务权限配置不可自动回退删除')

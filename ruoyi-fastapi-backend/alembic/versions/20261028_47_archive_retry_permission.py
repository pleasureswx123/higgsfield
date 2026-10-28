"""登记归档重试权限与项目角色的数据范围。"""

from alembic import op

revision = '20261028_47'
down_revision = '20261028_46'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '重试输出归档',menu_id,20,'','F','1','0','output:archive','migration_hf_47',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='output:archive')"
    )
    op.execute(
        "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) SELECT role_id,'output:archive',CASE WHEN code='owner' THEN 'project' ELSE 'own' END,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM hf_project_role WHERE code IN ('owner','producer') ON CONFLICT(role_id,permission_code) DO NOTHING"
    )


def downgrade():
    raise RuntimeError('业务权限配置不可自动回退删除')

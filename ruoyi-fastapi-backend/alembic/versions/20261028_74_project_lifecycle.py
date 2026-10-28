"""登记制作端归档权限及负责人项目权限，不自动授权系统角色。"""
from alembic import op

revision = '20261028_74'
down_revision = '20261028_73'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope)
        SELECT role_id,'project:archive','project' FROM hf_project_role WHERE code='owner'
        ON CONFLICT(role_id,permission_code) DO NOTHING""")
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '归档及恢复项目',menu_id,31,'','F','1','0','project:archive','migration_hf_74',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='project:archive')""")


def downgrade():
    raise RuntimeError('项目归档权限需显式处理既有授权，不自动删除')

"""登记制作端管理权限及负责人项目权限，不自动授权系统角色。"""
from alembic import op

revision = '20261028_75'
down_revision = '20261028_74'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope)
        SELECT role_id,'project:manage','project' FROM hf_project_role WHERE code='owner'
        ON CONFLICT(role_id,permission_code) DO NOTHING""")
    op.execute("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '编辑项目基本信息',menu_id,31,'','F','1','0','project:manage','migration_hf_75',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='project:manage')""")


def downgrade():
    raise RuntimeError('项目管理权限需显式处理既有授权，不自动删除')


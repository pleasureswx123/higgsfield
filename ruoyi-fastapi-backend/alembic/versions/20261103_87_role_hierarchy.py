"""补齐分层项目角色下载与负责人权限，移除不可用的取消生成授权。"""
from alembic import op

revision = '20261103_87'
down_revision = '20261102_86'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_by,update_by)
        SELECT role_id,'asset:download','project','migration_87','migration_87'
        FROM hf_project_role WHERE code IN ('viewer','producer','admin')
        ON CONFLICT(role_id,permission_code) DO NOTHING""")
    op.execute("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_by,update_by)
        SELECT a.role_id,p.permission_code,'project','migration_87','migration_87'
        FROM hf_project_role a CROSS JOIN hf_project_role_permission p
        JOIN hf_project_role r ON r.role_id=p.role_id
        WHERE a.code='admin' AND r.code IN ('viewer','producer')
        GROUP BY a.role_id,p.permission_code
        ON CONFLICT(role_id,permission_code) DO UPDATE SET data_scope='project',
            update_by='migration_87',update_time=CURRENT_TIMESTAMP""")
    op.execute("DELETE FROM hf_project_role_permission WHERE permission_code='generation:cancel'")


def downgrade():
    raise RuntimeError('权限变更需经审核后通过角色配置回退')

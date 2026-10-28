"""项目简报规范化与成员管理最小权限。"""

from alembic import op
from sqlalchemy import text

revision = '20261027_03'
down_revision = '20261027_02'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        text("UPDATE hf_project_brief SET body=CAST(:body AS jsonb) WHERE body='{}'::jsonb").bindparams(
            body='{"schemaVersion":1,"type":"doc","content":[]}'
        )
    )
    op.create_check_constraint('ck_hf_brief_revision', 'hf_project_brief', 'revision > 0')
    for role, permissions in {
        'owner': ['member:read', 'member:manage', 'project:edit'],
        'producer': ['member:read'],
        'viewer': ['member:read'],
    }.items():
        for permission in permissions:
            op.execute(
                text("""INSERT INTO hf_project_role_permission (role_id,permission_code,data_scope)
                SELECT role_id,:permission,'project' FROM hf_project_role WHERE code=:role
                ON CONFLICT (role_id,permission_code) DO NOTHING""").bindparams(role=role, permission=permission)
            )
    for label, permission in [
        ('查看项目成员', 'member:read'),
        ('管理项目成员', 'member:manage'),
        ('编辑项目简报', 'project:edit'),
    ]:
        op.execute(
            text("""INSERT INTO sys_menu
            (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
            SELECT :label,menu_id,2,'','F','1','0',:permission,'migration_hf_03',CURRENT_TIMESTAMP
            FROM sys_menu WHERE path='studio-project-permissions'
            AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(
                label=label, permission=permission
            )
        )


def downgrade():
    raise RuntimeError('权限及业务数据回退需要单独审核迁移')

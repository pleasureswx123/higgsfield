"""四级项目角色及唯一所有者，保留创建者历史。"""
from alembic import op
import sqlalchemy as sa
revision = '20261029_83'
down_revision = '20261029_82'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hf_project', sa.Column('owner_user_id', sa.BigInteger(), nullable=True, comment='当前所有者用户ID，转让不改变创建者'))
    op.execute("UPDATE hf_project SET owner_user_id=create_user_id")
    op.alter_column('hf_project', 'owner_user_id', nullable=False)
    op.execute("""INSERT INTO hf_project_role(code,role_name,is_system,create_by,update_by)
        VALUES ('admin','负责人','Y','migration_83','migration_83') ON CONFLICT(code) DO NOTHING""")
    op.execute("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_by,update_by)
        SELECT a.role_id,p.permission_code,p.data_scope,'migration_83','migration_83'
        FROM hf_project_role_permission p JOIN hf_project_role o ON o.role_id=p.role_id AND o.code='owner'
        CROSS JOIN hf_project_role a WHERE a.code='admin'
        ON CONFLICT(role_id,permission_code) DO NOTHING""")
    op.execute("""UPDATE hf_project_member m SET role_id=a.role_id,revision=m.revision+1,update_by='migration_83',update_time=CURRENT_TIMESTAMP
        FROM hf_project p,hf_project_role a,hf_project_role o
        WHERE m.project_id=p.project_id AND m.role_id=o.role_id AND o.code='owner' AND a.code='admin' AND m.user_id<>p.owner_user_id""")
    op.execute("""INSERT INTO hf_project_member(project_id,user_id,role_id,status,joined_time,revision,create_by,update_by)
        SELECT p.project_id,p.owner_user_id,r.role_id,'0',CURRENT_TIMESTAMP,1,'migration_83','migration_83'
        FROM hf_project p CROSS JOIN hf_project_role r WHERE r.code='owner'
        ON CONFLICT(project_id,user_id) DO UPDATE SET role_id=EXCLUDED.role_id,status='0',removed_time=NULL,
            revision=hf_project_member.revision+1,update_by='migration_83',update_time=CURRENT_TIMESTAMP""")
    op.execute("UPDATE hf_project_role SET role_name='Owner（项目所有者）' WHERE code='owner'")
    op.execute("""UPDATE hf_project_permission_config SET overrides=(overrides-'owner') ||
        CASE WHEN overrides ? 'owner' THEN jsonb_build_object('admin',overrides->'owner') ELSE '{}'::jsonb END,
        revision=revision+1,update_by='migration_83',update_time=CURRENT_TIMESTAMP""")
    # 迁移中固化权限清单，不依赖后续业务常量变化。
    permissions = """project:read project:edit project:manage project:archive member:read member:manage asset:read asset:upload asset:create asset:edit asset:reference asset:remove asset:download folder:write element:read element:create element:edit element:remove element:configure element:import element:copy content:review generation:create generation:read generation:cancel output:archive comment:read comment:create comment:edit:own comment:moderate project:usage:read""".split()
    connection = op.get_bind()
    for code in permissions:
        connection.execute(sa.text("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_by,update_by)
            SELECT role_id,:code,'project','migration_83','migration_83' FROM hf_project_role WHERE code='owner'
            ON CONFLICT(role_id,permission_code) DO UPDATE SET data_scope='project'"""), {'code': code})
    owner_role = int(connection.scalar(sa.text("SELECT role_id FROM hf_project_role WHERE code='owner'")))
    op.create_index('uq_hf_project_active_owner','hf_project_member',['project_id'],unique=True,
        postgresql_where=sa.text(f"status='0' AND role_id={owner_role}"))


def downgrade():
    raise RuntimeError('所有权迁移不可自动回退，需审核当前所有权与历史记录')

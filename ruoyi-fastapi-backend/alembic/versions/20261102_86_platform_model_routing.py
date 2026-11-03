"""全平台默认模型路由，保留全部项目专用配置。"""
from alembic import op
import sqlalchemy as sa

revision = '20261102_86'
down_revision = '20261030_85'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('hf_project_routing_set', 'project_id', existing_type=sa.BigInteger(), nullable=True,
                    comment='所属项目ID，空值为全平台默认组')
    op.alter_column('hf_project_provider_config', 'project_id', existing_type=sa.BigInteger(), nullable=True,
                    comment='所属项目及路由组ID，空值为全平台默认路由')
    op.create_index('uq_hf_platform_routing_set', 'hf_project_routing_set', [sa.text('(1)')],
                    unique=True, postgresql_where=sa.text('project_id IS NULL'))
    op.create_index('uq_hf_platform_model_account', 'hf_project_provider_config', ['model_id', 'account_id'],
                    unique=True, postgresql_where=sa.text('project_id IS NULL'))
    op.execute("INSERT INTO hf_project_routing_set (project_id, revision, create_by, update_by, create_time, update_time) "
               "VALUES (NULL, 1, 'migration', 'migration', NOW(), NOW())")


def downgrade():
    # 不静默删除已生效的平台配置，先由管理员清空后才能降级。
    if op.get_bind().scalar(sa.text('SELECT count(*) FROM hf_project_provider_config WHERE project_id IS NULL')):
        raise ValueError('全平台模型配置仍存在，不能直接降级')
    op.execute('DELETE FROM hf_project_routing_set WHERE project_id IS NULL')
    op.drop_index('uq_hf_platform_model_account', table_name='hf_project_provider_config')
    op.drop_index('uq_hf_platform_routing_set', table_name='hf_project_routing_set')
    op.alter_column('hf_project_provider_config', 'project_id', existing_type=sa.BigInteger(), nullable=False,
                    comment='所属项目及路由组ID')
    op.alter_column('hf_project_routing_set', 'project_id', existing_type=sa.BigInteger(), nullable=False,
                    comment='所属项目ID，一个项目一组')

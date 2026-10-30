"""项目独立角色权限配置。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '20261029_82'
down_revision = '20261029_81'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('hf_project_permission_config',
        sa.Column('config_id', sa.BigInteger(), primary_key=True, autoincrement=True, comment='配置ID'),
        sa.Column('project_id', sa.BigInteger(), nullable=False, comment='项目ID'),
        sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1', comment='并发版本'),
        sa.Column('overrides', JSONB(), nullable=False, server_default='{}', comment='按角色代码保存权限覆盖及范围，none表示禁用'),
        sa.Column('create_by', sa.String(64), nullable=False, server_default='', comment='创建者'),
        sa.Column('update_by', sa.String(64), nullable=False, server_default='', comment='更新者'),
        sa.Column('create_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('update_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='更新时间'),
        sa.UniqueConstraint('project_id', name='uq_hf_project_permission_config_project'),
        sa.CheckConstraint('project_id > 0 AND revision > 0', name='ck_hf_project_permission_config_positive'),
        comment='项目角色权限配置')


def downgrade():
    raise RuntimeError('权限配置属于授权记录，不允许自动删除回退')

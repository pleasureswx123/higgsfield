"""添加讨论状态颜色标签。"""
from alembic import op
import sqlalchemy as sa
revision = '20261030_85'
down_revision = '20261030_84'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hf_comment_thread', sa.Column('status_color', sa.String(7), nullable=True, comment='讨论状态标签颜色，空值表示无标签'))
    op.create_check_constraint('ck_hf_comment_thread_status_color', 'hf_comment_thread', "status_color IS NULL OR status_color IN ('#ffffff','#fa551e','#f39c20','#f4d42a','#7bd65b','#4798fa','#8257ef')")


def downgrade():
    op.drop_constraint('ck_hf_comment_thread_status_color', 'hf_comment_thread', type_='check')
    op.drop_column('hf_comment_thread', 'status_color')

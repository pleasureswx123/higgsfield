"""固定元素修订的人物性质；旧修订保持普通引用，新角色由创建服务默认开启。"""
from alembic import op
import sqlalchemy as sa

revision = '20261109_90'
down_revision = '20261109_89'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hf_element_revision', sa.Column('is_fictional_person', sa.Boolean(), nullable=False,
        server_default=sa.text('false'), comment='是否虚构人物，固定修订中的人物素材注册策略'))


def downgrade():
    op.drop_column('hf_element_revision', 'is_fictional_person')

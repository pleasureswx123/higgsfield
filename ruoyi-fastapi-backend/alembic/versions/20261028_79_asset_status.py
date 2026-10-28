"""为素材增加持久化工作状态，不改变已有权限。"""
from alembic import op
import sqlalchemy as sa
revision = '20261028_79'
down_revision = '20261028_78'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('hf_asset', sa.Column('work_status', sa.String(16), nullable=False, server_default='none', comment='素材工作状态：none无状态、working进行中、review待审核、approved已通过、rejected已驳回'))
    op.create_check_constraint('ck_hf_asset_work_status', 'hf_asset', "work_status IN ('none','working','review','approved','rejected')")

def downgrade():
    op.drop_constraint('ck_hf_asset_work_status', 'hf_asset', type_='check')
    op.drop_column('hf_asset', 'work_status')

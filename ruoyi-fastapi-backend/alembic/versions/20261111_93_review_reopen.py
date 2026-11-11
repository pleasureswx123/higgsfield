"""重新制作动作与元素分类的固定修订证据。"""
from alembic import op
import sqlalchemy as sa

revision = '20261111_93'
down_revision = '20261111_92'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hf_element_revision', sa.Column('category_snapshot', sa.String(32),
        comment='此修订审核时的元素分类，空表示旧修订未知'))
    op.create_check_constraint('ck_hf_element_revision_category', 'hf_element_revision',
        "category_snapshot IS NULL OR category_snapshot IN ('character','scene','prop','other')")
    op.drop_constraint('ck_hf_review_action', 'hf_review_event', type_='check')
    op.create_check_constraint('ck_hf_review_action', 'hf_review_event',
        "action IN ('legacy','start','submit','withdraw','request_changes','approve','revise','reopen')")


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM hf_review_event WHERE action='reopen') "
        "OR EXISTS(SELECT 1 FROM hf_element_revision WHERE category_snapshot IS NOT NULL)")):
        raise RuntimeError('已有重新制作或分类快照证据，不能回滚并丢失业务证据')
    op.drop_constraint('ck_hf_review_action', 'hf_review_event', type_='check')
    op.create_check_constraint('ck_hf_review_action', 'hf_review_event',
        "action IN ('legacy','start','submit','withdraw','request_changes','approve','revise')")
    op.drop_constraint('ck_hf_element_revision_category', 'hf_element_revision', type_='check')
    op.drop_column('hf_element_revision', 'category_snapshot')

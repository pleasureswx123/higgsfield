"""制作责任与绑定版本的审核证据；不推测旧状态对应的版本。"""
from alembic import op
import sqlalchemy as sa

revision = '20261111_92'
down_revision = '20261109_91'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('hf_asset', sa.Column('performer_id', sa.BigInteger(), comment='当前制作责任人用户ID，空时由作者制作'))
    for name, comment in (
        ('asset_id', '素材目标ID'),
        ('asset_version_id', '此次操作的固定素材版本ID'),
        ('element_revision_id', '此次操作的固定元素修订ID'),
    ):
        op.add_column('hf_review_event', sa.Column(name, sa.BigInteger(), comment=comment))
    op.add_column('hf_review_event', sa.Column('action', sa.String(32), nullable=False,
        server_default='legacy', comment='业务动作，legacy表示未绑定版本的历史状态记录'))
    op.drop_constraint('ck_hf_review_target', 'hf_review_event', type_='check')
    op.create_check_constraint('ck_hf_review_target', 'hf_review_event', 'num_nonnulls(element_id,output_id,asset_id)=1')
    op.create_check_constraint('ck_hf_review_action', 'hf_review_event',
        "action IN ('legacy','start','submit','withdraw','request_changes','approve','revise')")
    op.create_check_constraint('ck_hf_review_version_target', 'hf_review_event',
        "(action = 'legacy' AND asset_version_id IS NULL AND element_revision_id IS NULL) OR "
        "(action != 'legacy' AND ((asset_id IS NOT NULL AND asset_version_id IS NOT NULL "
        "AND element_revision_id IS NULL) OR (element_id IS NOT NULL "
        "AND element_revision_id IS NOT NULL AND asset_version_id IS NULL)))")
    op.create_index('ix_hf_review_asset', 'hf_review_event', ['asset_id', 'review_event_id'])


def downgrade():
    # 不允许回滚时静默丢失审核证据或责任分配。
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM hf_review_event WHERE action <> 'legacy') "
                                 "OR EXISTS(SELECT 1 FROM hf_asset WHERE performer_id IS NOT NULL)")):
        raise RuntimeError('已有版本审核记录或制作责任分配，不能回滚并丢失业务证据')
    op.drop_index('ix_hf_review_asset', table_name='hf_review_event')
    for name in ('ck_hf_review_version_target', 'ck_hf_review_action', 'ck_hf_review_target'):
        op.drop_constraint(name, 'hf_review_event', type_='check')
    op.create_check_constraint('ck_hf_review_target', 'hf_review_event', 'num_nonnulls(element_id,output_id)=1')
    for name in ('action', 'element_revision_id', 'asset_version_id', 'asset_id'):
        op.drop_column('hf_review_event', name)
    op.drop_column('hf_asset', 'performer_id')

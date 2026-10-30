"""评论协作状态与表情回应，保留已有评论。"""
from alembic import op
import sqlalchemy as sa
revision = '20261029_80'
down_revision = '20261028_79'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('hf_comment_thread', sa.Column('revision', sa.BigInteger(), nullable=False, server_default='1', comment='讨论并发修订'))
    op.add_column('hf_comment_thread', sa.Column('del_flag', sa.CHAR(1), nullable=False, server_default='0', comment='0存在2删除'))
    op.create_table('hf_comment_reaction',
        sa.Column('reaction_id', sa.BigInteger(), primary_key=True, autoincrement=True, comment='回应ID'),
        sa.Column('comment_id', sa.BigInteger(), nullable=False, comment='评论ID'),
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='回应用户ID'),
        sa.Column('emoji', sa.String(32), nullable=False, comment='表情字符'),
        sa.Column('del_flag', sa.CHAR(1), nullable=False, server_default='0', comment='0存在2取消'),
        sa.Column('create_by', sa.String(64), nullable=False, server_default='', comment='创建者'),
        sa.Column('update_by', sa.String(64), nullable=False, server_default='', comment='更新者'),
        sa.Column('create_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('update_time', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment='更新时间'),
        sa.UniqueConstraint('comment_id', 'user_id', 'emoji', name='uq_hf_comment_reaction_actor'),
        sa.CheckConstraint("comment_id > 0 AND user_id > 0 AND del_flag IN ('0','2')", name='ck_hf_comment_reaction_fields'),
        comment='评论表情回应')

def downgrade():
    op.drop_table('hf_comment_reaction')
    op.drop_column('hf_comment_thread', 'del_flag')
    op.drop_column('hf_comment_thread', 'revision')

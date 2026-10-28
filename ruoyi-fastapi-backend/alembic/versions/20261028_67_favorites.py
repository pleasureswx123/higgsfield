"""个人收藏关系；取消收藏逻辑删除，再次收藏复用身份，不授予对象权限。"""
from alembic import op

revision = '20261028_67'
down_revision = '20261028_66'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_favorite (
        favorite_id bigserial PRIMARY KEY, user_id bigint NOT NULL,
        element_id bigint, asset_id bigint, output_id bigint,
        del_flag char(1) NOT NULL DEFAULT '0',
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT ck_hf_favorite_target CHECK(user_id>0 AND num_nonnulls(element_id,asset_id,output_id)=1
            AND (element_id IS NULL OR element_id>0) AND (asset_id IS NULL OR asset_id>0)
            AND (output_id IS NULL OR output_id>0) AND del_flag IN ('0','2')))""")
    for target in ('element_id', 'asset_id', 'output_id'):
        op.execute(f'CREATE UNIQUE INDEX uq_hf_favorite_{target} ON hf_favorite(user_id,{target}) WHERE {target} IS NOT NULL')
    op.execute('CREATE INDEX ix_hf_favorite_user ON hf_favorite(user_id,del_flag,create_time,favorite_id)')
    op.execute("COMMENT ON TABLE hf_favorite IS '个人收藏关系，不创建内容访问授权'")
    for name, comment in {'favorite_id': '收藏ID', 'user_id': '收藏用户ID', 'element_id': '目标元素ID',
        'asset_id': '目标素材ID', 'output_id': '目标作品ID', 'del_flag': '收藏状态：0存在2取消',
        'create_by': '创建者', 'update_by': '更新者', 'create_time': '创建时间', 'update_time': '更新时间'}.items():
        op.execute(f"COMMENT ON COLUMN hf_favorite.{name} IS '{comment}'")


def downgrade():
    raise RuntimeError('个人收藏关系不得通过自动降级删除，请先制定数据保留方案')

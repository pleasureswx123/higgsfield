"""固定版本评论、同线程回复及图片定位标注基础。"""
from alembic import op

revision = '20261028_68'
down_revision = '20261028_67'
branch_labels = None
depends_on = None


def upgrade():
    audit = """create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL"""
    op.execute(f"""CREATE TABLE hf_comment_thread (
        thread_id bigserial PRIMARY KEY, asset_version_id bigint, output_id bigint,
        create_user_id bigint NOT NULL, resolved_time timestamptz(3), {audit},
        CONSTRAINT ck_hf_comment_thread_target CHECK(num_nonnulls(asset_version_id,output_id)=1
            AND create_user_id>0 AND (asset_version_id IS NULL OR asset_version_id>0)
            AND (output_id IS NULL OR output_id>0)))""")
    op.execute(f"""CREATE TABLE hf_comment (
        comment_id bigserial PRIMARY KEY, thread_id bigint NOT NULL, parent_id bigint,
        author_id bigint NOT NULL, body text NOT NULL, video_time numeric(18,6),
        revision bigint NOT NULL DEFAULT 1, del_flag char(1) NOT NULL DEFAULT '0', {audit},
        CONSTRAINT uq_hf_comment_thread_identity UNIQUE(comment_id,thread_id),
        CONSTRAINT ck_hf_comment_fields CHECK(thread_id>0 AND author_id>0 AND revision>0
            AND del_flag IN ('0','2') AND (parent_id IS NULL OR (parent_id>0 AND parent_id<>comment_id))
            AND (video_time IS NULL OR video_time>=0)
            AND char_length(btrim(body))>0 AND char_length(body)<=5000))""")
    op.execute(f"""CREATE TABLE hf_annotation (
        annotation_id bigserial PRIMARY KEY, comment_id bigint NOT NULL, shape varchar(32) NOT NULL,
        geometry jsonb NOT NULL, color varchar(16) NOT NULL,
        source_width integer NOT NULL, source_height integer NOT NULL, {audit},
        CONSTRAINT ck_hf_annotation_fields CHECK(comment_id>0 AND shape IN ('point','rect','path')
            AND jsonb_typeof(geometry)='object' AND color ~ '^#[0-9a-f]{{6}}$'
            AND source_width>0 AND source_width<=100000 AND source_height>0 AND source_height<=100000))""")
    for statement in (
        'CREATE INDEX ix_hf_comment_thread_asset ON hf_comment_thread(asset_version_id,create_time)',
        'CREATE INDEX ix_hf_comment_thread_output ON hf_comment_thread(output_id,create_time)',
        'CREATE INDEX ix_hf_comment_thread_time ON hf_comment(thread_id,create_time,comment_id)',
        'CREATE INDEX ix_hf_annotation_comment ON hf_annotation(comment_id)',
    ):
        op.execute(statement)
    tables = {
        'hf_comment_thread': ('评论主题及固定版本目标', {'thread_id': '评论主题ID', 'asset_version_id': '固定素材版本ID',
            'output_id': '固定作品ID', 'create_user_id': '主题发起人ID', 'resolved_time': '协作处理时间'}),
        'hf_comment': ('评论正文及同主题回复', {'comment_id': '评论ID', 'thread_id': '固定主题ID', 'parent_id': '同主题父评论ID',
            'author_id': '评论作者ID', 'body': '纯文本评论正文', 'video_time': '视频定位秒数', 'revision': '评论并发修订', 'del_flag': '0存在2删除'}),
        'hf_annotation': ('随评论修订整体替换的图片定位标注', {'annotation_id': '图片标注ID', 'comment_id': '所属评论ID',
            'shape': '形状：point点rect矩形path路径', 'geometry': '归一化坐标形状数据', 'color': '小写六位十六进制颜色',
            'source_width': '标注原图像素宽度', 'source_height': '标注原图像素高度'}),
    }
    for table, (description, fields) in tables.items():
        op.execute(f"COMMENT ON TABLE {table} IS '{description}'")
        for name, comment in (fields | {'create_by': '创建者', 'update_by': '更新者', 'create_time': '创建时间', 'update_time': '更新时间'}).items():
            op.execute(f"COMMENT ON COLUMN {table}.{name} IS '{comment}'")


def downgrade():
    raise RuntimeError('评论协作历史不得通过自动降级删除，请先制定保留与恢复方案')

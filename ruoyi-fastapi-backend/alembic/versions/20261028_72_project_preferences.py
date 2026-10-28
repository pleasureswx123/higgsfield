"""个人集合和项目导航偏好，不修改项目权限。"""
from alembic import op

revision = '20261028_72'
down_revision = '20261028_71'
branch_labels = None
depends_on = None


def upgrade():
    audit = "create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '', create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL"
    op.execute(f"""CREATE TABLE hf_project_collection (
        collection_id bigserial PRIMARY KEY, user_id bigint NOT NULL, collection_name varchar(200) NOT NULL,
        description text, color varchar(7), order_num integer NOT NULL DEFAULT 0, revision bigint NOT NULL DEFAULT 1, {audit},
        CONSTRAINT uq_hf_collection_user_name UNIQUE(user_id,collection_name),
        CONSTRAINT ck_hf_collection_fields CHECK(user_id>0 AND revision>0 AND char_length(btrim(collection_name))>0),
        CONSTRAINT ck_hf_collection_color CHECK(color IS NULL OR color ~ '^#[0-9a-f]{{6}}$'),
        CONSTRAINT ck_hf_collection_description CHECK(description IS NULL OR char_length(description)<=2000))""")
    op.execute(f"""CREATE TABLE hf_user_project_preference (
        preference_id bigserial PRIMARY KEY, user_id bigint NOT NULL, project_id bigint NOT NULL, collection_id bigint,
        is_pinned char(1) NOT NULL DEFAULT 'N', is_hidden char(1) NOT NULL DEFAULT 'N',
        order_num integer NOT NULL DEFAULT 0, revision bigint NOT NULL DEFAULT 1, {audit},
        CONSTRAINT uq_hf_preference_user_project UNIQUE(user_id,project_id),
        CONSTRAINT ck_hf_project_preference_fields CHECK(user_id>0 AND project_id>0 AND revision>0
            AND (collection_id IS NULL OR collection_id>0) AND is_pinned IN ('Y','N') AND is_hidden IN ('Y','N')))""")
    op.execute('CREATE INDEX ix_hf_collection_user_order ON hf_project_collection(user_id,order_num,collection_id)')
    op.execute('CREATE INDEX ix_hf_preference_user_flags_order ON hf_user_project_preference(user_id,is_hidden,is_pinned,order_num)')
    tables = {
        'hf_project_collection': ('个人项目集合，不授予项目访问权', {'collection_id': '集合ID', 'user_id': '所属用户ID', 'collection_name': '集合名称', 'description': '集合说明', 'color': '个人集合颜色', 'order_num': '个人排序', 'revision': '并发修订'}),
        'hf_user_project_preference': ('项目个人导航偏好，不改变成员或项目状态', {'preference_id': '偏好ID', 'user_id': '所属用户ID', 'project_id': '项目ID', 'collection_id': '本人集合ID', 'is_pinned': '是否置顶：Y是N否', 'is_hidden': '是否隐藏：Y是N否', 'order_num': '个人排序', 'revision': '并发修订'}),
    }
    for table, (label, fields) in tables.items():
        op.execute(f"COMMENT ON TABLE {table} IS '{label}'")
        for field, description in (fields | {'create_by': '创建者', 'update_by': '更新者', 'create_time': '创建时间', 'update_time': '更新时间'}).items():
            op.execute(f"COMMENT ON COLUMN {table}.{field} IS '{description}'")


def downgrade():
    raise RuntimeError('个人集合和偏好可能已有用户数据，降级前须制定保留方案')

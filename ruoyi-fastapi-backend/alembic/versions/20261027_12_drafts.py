"""私有生成草稿及结构化引用，真实 PostgreSQL 迁移。"""

from alembic import op

revision = '20261027_12'
down_revision = '20261027_11'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_prompt_draft (\n\tdraft_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT NOT NULL, \n\towner_id BIGINT NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tbody JSONB NOT NULL, \n\tschema_version INTEGER DEFAULT '1' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (draft_id), \n\tCONSTRAINT uq_hf_draft_project UNIQUE (draft_id, project_id), \n\tCONSTRAINT ck_hf_draft_state CHECK (kind IN ('image','video','chat') AND revision > 0 AND schema_version = 1)\n)"
    )
    op.execute("COMMENT ON TABLE hf_prompt_draft IS '本人私有创作草稿'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.draft_id IS '草稿ID'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.project_id IS '所属项目ID'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.owner_id IS '草稿所有者用户ID'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.kind IS '创作类型'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.body IS '白名单提示词和参数草稿'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.schema_version IS '结构契约版本'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_prompt_draft.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_draft_owner ON hf_prompt_draft (owner_id, project_id, update_time, draft_id)')
    op.execute(
        "CREATE TABLE hf_draft_reference (\n\treference_id BIGSERIAL NOT NULL, \n\tdraft_id BIGINT NOT NULL, \n\treference_key BIGINT NOT NULL, \n\tasset_version_id BIGINT NOT NULL, \n\telement_revision_id BIGINT, \n\tmedia_role VARCHAR(32) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (reference_id), \n\tCONSTRAINT uq_hf_draft_reference UNIQUE (draft_id, reference_key, ordinal), \n\tCONSTRAINT ck_hf_draft_reference_order CHECK (ordinal >= 0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_draft_reference IS '草稿固定媒体引用关系'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.reference_id IS '引用行主键'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.draft_id IS '草稿ID'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.reference_key IS '编辑器提及稳定键'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.asset_version_id IS '固定素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.element_revision_id IS '固定元素修订ID'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.media_role IS '媒体输入角色'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.ordinal IS '用户选择顺序'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_draft_reference.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_draft_reference_order ON hf_draft_reference (draft_id, ordinal)')


def downgrade():
    raise RuntimeError('草稿数据不可自动回退删除')

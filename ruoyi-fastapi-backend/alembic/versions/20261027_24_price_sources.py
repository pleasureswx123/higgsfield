"""价格来源与版本证据关联的真实迁移。"""

from alembic import op

revision = '20261027_24'
down_revision = '20261027_23'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_price_source (\n\tsource_id BIGSERIAL NOT NULL, \n\tsource_type VARCHAR(32) NOT NULL, \n\tsource_url TEXT, \n\texcerpt TEXT NOT NULL, \n\tfile_id BIGINT, \n\tobserved_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tcreate_user_id BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (source_id), \n\tCONSTRAINT ck_hf_price_source_type CHECK (source_type IN ('vendor_document','official_screenshot','manual_confirmation') AND length(btrim(excerpt))>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_source IS '不可变价格来源证据'")
    op.execute("COMMENT ON COLUMN hf_price_source.source_id IS '价格来源ID'")
    op.execute("COMMENT ON COLUMN hf_price_source.source_type IS '供应商文档、官方截图或人工确认'")
    op.execute("COMMENT ON COLUMN hf_price_source.source_url IS '来源出处地址，不自动抓取'")
    op.execute("COMMENT ON COLUMN hf_price_source.excerpt IS '原文摘录及确认依据'")
    op.execute("COMMENT ON COLUMN hf_price_source.file_id IS '管理受控证据附件ID'")
    op.execute("COMMENT ON COLUMN hf_price_source.observed_time IS '证据获取时间'")
    op.execute("COMMENT ON COLUMN hf_price_source.create_user_id IS '证据录入用户ID'")
    op.execute("COMMENT ON COLUMN hf_price_source.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_source.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_source.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_source.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_price_source_observed ON hf_price_source (source_type, observed_time)')
    op.execute(
        "CREATE TABLE hf_price_version_source (\n\tversion_source_id BIGSERIAL NOT NULL, \n\tprice_version_id BIGINT NOT NULL, \n\tsource_id BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (version_source_id), \n\tCONSTRAINT uq_hf_price_version_source UNIQUE (price_version_id, source_id)\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_version_source IS '价格版本与来源证据关联'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.version_source_id IS '版本来源关联ID'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.price_version_id IS '价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.source_id IS '价格来源证据ID'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_version_source.update_time IS '更新时间'")


def downgrade():
    op.execute('DROP TABLE hf_price_version_source')
    op.execute('DROP TABLE hf_price_source')

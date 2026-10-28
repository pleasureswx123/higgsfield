"""汇率历史版本的 PostgreSQL 迁移。"""

from alembic import op

revision = '20261027_26'
down_revision = '20261027_25'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_exchange_rate_version (\n\texchange_rate_id BIGSERIAL NOT NULL, \n\tbase_currency VARCHAR(3) NOT NULL, \n\tquote_currency VARCHAR(3) NOT NULL, \n\trate NUMERIC(24, 12) NOT NULL, \n\tvalid_from TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tvalid_until TIMESTAMP(3) WITH TIME ZONE, \n\tsource_id BIGINT NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (exchange_rate_id), \n\tCONSTRAINT ck_hf_exchange_rate_version CHECK (base_currency ~ '^[A-Z]{3}$' AND quote_currency ~ '^[A-Z]{3}$' AND base_currency<>quote_currency AND rate>0 AND revision>0 AND status IN ('0','1') AND (valid_until IS NULL OR valid_until>valid_from))\n)"
    )
    op.execute("COMMENT ON TABLE hf_exchange_rate_version IS '汇率版本及历史适用区间'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.exchange_rate_id IS '汇率版本ID'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.base_currency IS '基础币种'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.quote_currency IS '计价币种'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.rate IS '一单位基础币兑换计价币的数量'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.valid_from IS '有效起点，含'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.valid_until IS '有效终点，不含，空为无穷'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.source_id IS '来源证据ID'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.status IS '状态：0草稿1已发布'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_exchange_rate_version.update_time IS '更新时间'")
    op.execute(
        'CREATE INDEX ix_hf_exchange_rate_pair ON hf_exchange_rate_version (base_currency, quote_currency, status, valid_from)'
    )


def downgrade():
    op.execute('DROP TABLE hf_exchange_rate_version')

"""价格簿、版本和分项的 PostgreSQL 真实迁移。"""

from alembic import op

revision = '20261027_22'
down_revision = '20261027_21'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_price_book (\n\tprice_book_id BIGSERIAL NOT NULL, \n\tmodel_variant_id BIGINT NOT NULL, \n\tpurpose VARCHAR(32) NOT NULL, \n\taccount_id BIGINT, \n\tcurrency VARCHAR(3) NOT NULL, \n\tprice_book_name VARCHAR(200) NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (price_book_id), \n\tCONSTRAINT ck_hf_price_book_scope CHECK ((purpose='platform' AND account_id IS NULL) OR (purpose='procurement' AND account_id IS NOT NULL)), \n\tCONSTRAINT ck_hf_price_book_currency CHECK (currency ~ '^[A-Z]{3}$')\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_book IS '价格用途与账号作用域'")
    op.execute("COMMENT ON COLUMN hf_price_book.price_book_id IS '价格簿ID'")
    op.execute("COMMENT ON COLUMN hf_price_book.model_variant_id IS '完整模型规格ID'")
    op.execute("COMMENT ON COLUMN hf_price_book.purpose IS '价格用途：platform平台价或procurement采购价'")
    op.execute("COMMENT ON COLUMN hf_price_book.account_id IS '采购账号ID，平台价为空'")
    op.execute("COMMENT ON COLUMN hf_price_book.currency IS '计价币种代码'")
    op.execute("COMMENT ON COLUMN hf_price_book.price_book_name IS '价格簿名称'")
    op.execute("COMMENT ON COLUMN hf_price_book.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_book.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_book.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_book.update_time IS '更新时间'")
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_price_book_account ON hf_price_book (model_variant_id, purpose, currency, account_id) WHERE account_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_price_book_platform ON hf_price_book (model_variant_id, purpose, currency) WHERE account_id IS NULL'
    )
    op.execute(
        "CREATE TABLE hf_price_version (\n\tprice_version_id BIGSERIAL NOT NULL, \n\tprice_book_id BIGINT NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\trounding_mode VARCHAR(32) NOT NULL, \n\tcalculation_scale INTEGER NOT NULL, \n\tschema_version INTEGER DEFAULT '1' NOT NULL, \n\tcreate_user_id BIGINT NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (price_version_id), \n\tCONSTRAINT uq_hf_price_version_no UNIQUE (price_book_id, version_no), \n\tCONSTRAINT uq_hf_price_version_identity UNIQUE (price_book_id, price_version_id), \n\tCONSTRAINT ck_hf_price_version_state CHECK (version_no>0 AND revision>0 AND schema_version=1 AND status IN ('0','1') AND rounding_mode='half_up' AND calculation_scale BETWEEN 0 AND 10)\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_version IS '价格版本内容，发布后不可修改'")
    op.execute("COMMENT ON COLUMN hf_price_version.price_version_id IS '价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_price_version.price_book_id IS '所属价格簿ID'")
    op.execute("COMMENT ON COLUMN hf_price_version.version_no IS '价格簿内版本号'")
    op.execute("COMMENT ON COLUMN hf_price_version.status IS '状态：0草稿1已发布'")
    op.execute("COMMENT ON COLUMN hf_price_version.rounding_mode IS '舍入方式：half_up'")
    op.execute("COMMENT ON COLUMN hf_price_version.calculation_scale IS '显式指定计算保留位数，0到10'")
    op.execute("COMMENT ON COLUMN hf_price_version.schema_version IS '价格模板结构版本'")
    op.execute("COMMENT ON COLUMN hf_price_version.create_user_id IS '价格编辑者用户ID'")
    op.execute("COMMENT ON COLUMN hf_price_version.revision IS '草稿并发版本'")
    op.execute("COMMENT ON COLUMN hf_price_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_version.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_price_rule_item (\n\titem_id BIGSERIAL NOT NULL, \n\tprice_version_id BIGINT NOT NULL, \n\titem_code VARCHAR(100) NOT NULL, \n\tunit VARCHAR(32) NOT NULL, \n\tunit_quantity NUMERIC(18, 6) NOT NULL, \n\tunit_price NUMERIC(24, 10) NOT NULL, \n\tquantity_from NUMERIC(24, 6) DEFAULT '0' NOT NULL, \n\tquantity_to NUMERIC(24, 6), \n\tformula_template VARCHAR(100) NOT NULL, \n\tfree_reason TEXT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (item_id), \n\tCONSTRAINT uq_hf_price_item_start UNIQUE (price_version_id, item_code, quantity_from), \n\tCONSTRAINT ck_hf_price_item_numbers CHECK (unit_quantity>0 AND unit_price>=0 AND quantity_from>=0 AND (quantity_to IS NULL OR quantity_to>quantity_from)), \n\tCONSTRAINT ck_hf_price_item_free_reason CHECK (unit_price>0 OR (free_reason IS NOT NULL AND length(btrim(free_reason))>0)), \n\tCONSTRAINT ck_hf_price_item_template CHECK (unit IN ('token','image','second','character') AND formula_template IN ('linear','tiered'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_rule_item IS '价格计费分项及累计阶梯'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.item_id IS '价格分项ID'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.price_version_id IS '所属价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.item_code IS '计费用量分项代码'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.unit IS '用量单位'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.unit_quantity IS '单价对应的数量基数'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.unit_price IS '基数对应单价，零价需说明'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.quantity_from IS '累计阶梯下限，含'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.quantity_to IS '累计阶梯上限，不含，空为无穷'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.formula_template IS '受控公式模板键'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.free_reason IS '明确免费依据'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_rule_item.update_time IS '更新时间'")


def downgrade():
    op.execute('DROP TABLE hf_price_rule_item')
    op.execute('DROP TABLE hf_price_version')
    op.execute('DROP TABLE hf_price_book')

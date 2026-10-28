"""计价事件、分项证据及调整的固定DDL。"""

from alembic import op

revision = '20261027_39'
down_revision = '20261027_38'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE hf_billing_event (\n\tevent_id BIGSERIAL NOT NULL, \n\tsubject_id BIGINT NOT NULL, \n\tusage_record_id BIGINT, \n\tpurpose VARCHAR(32) NOT NULL, \n\tprice_version_id BIGINT NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tamount NUMERIC(24, 10), \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (event_id), \n\tCONSTRAINT uq_hf_billing_event_purpose UNIQUE (subject_id, purpose), \n\tCONSTRAINT ck_hf_billing_event_state CHECK (purpose IN ('platform','procurement') AND currency ~ '^[A-Z]{3}$' AND state IN ('0','1','2','3') AND revision>0), \n\tCONSTRAINT ck_hf_billing_event_amount CHECK ((amount IS NULL OR amount>=0) AND (state NOT IN ('1','2') OR amount IS NOT NULL))\n)\n\n"
    )
    op.execute("COMMENT ON TABLE hf_billing_event IS '分口径计价结果，不同口径不代表重复消费'")
    op.execute("COMMENT ON COLUMN hf_billing_event.event_id IS '计价事件ID'")
    op.execute("COMMENT ON COLUMN hf_billing_event.subject_id IS '上游计费对象ID'")
    op.execute("COMMENT ON COLUMN hf_billing_event.usage_record_id IS '采用的用量修订ID，未知为空'")
    op.execute("COMMENT ON COLUMN hf_billing_event.purpose IS '计价口径：platform平台procurement采购'")
    op.execute("COMMENT ON COLUMN hf_billing_event.price_version_id IS '固定价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_billing_event.currency IS '计价原币种'")
    op.execute("COMMENT ON COLUMN hf_billing_event.amount IS '首次确定的金额，未知为空'")
    op.execute("COMMENT ON COLUMN hf_billing_event.state IS '计价状态：0待定1已计算2已确认3有争议'")
    op.execute("COMMENT ON COLUMN hf_billing_event.revision IS '计价并发版本'")
    op.execute("COMMENT ON COLUMN hf_billing_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_billing_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_billing_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_billing_event.update_time IS '更新时间'")
    op.execute(
        "\nCREATE TABLE hf_billing_line_item (\n\tline_item_id BIGSERIAL NOT NULL, \n\tevent_id BIGINT NOT NULL, \n\trule_item_id BIGINT NOT NULL, \n\tquantity NUMERIC(24, 6) NOT NULL, \n\tunit_quantity NUMERIC(18, 6) NOT NULL, \n\tunit_price NUMERIC(24, 10) NOT NULL, \n\tamount NUMERIC(24, 10) NOT NULL, \n\tcalculation_snapshot JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (line_item_id), \n\tCONSTRAINT uq_hf_billing_line_rule UNIQUE (event_id, rule_item_id), \n\tCONSTRAINT ck_hf_billing_line_values CHECK (quantity>=0 AND unit_quantity>0 AND unit_price>=0 AND amount>=0), \n\tCONSTRAINT ck_hf_billing_line_snapshot CHECK (jsonb_typeof(calculation_snapshot)='object')\n)\n\n"
    )
    op.execute("COMMENT ON TABLE hf_billing_line_item IS '不可变计价分项证据'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.line_item_id IS '计价明细ID'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.event_id IS '计价事件ID'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.rule_item_id IS '命中价格分项ID'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.quantity IS '参与计价的用量'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.unit_quantity IS '计价基数快照'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.unit_price IS '单价快照'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.amount IS '分项金额'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.calculation_snapshot IS '计算公式及舍入证据快照'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_billing_line_item.update_time IS '更新时间'")
    op.execute(
        "\nCREATE TABLE hf_billing_adjustment (\n\tadjustment_id BIGSERIAL NOT NULL, \n\tevent_id BIGINT NOT NULL, \n\tusage_record_id BIGINT, \n\treconciliation_line_id BIGINT, \n\tadjustment_key VARCHAR(200) NOT NULL, \n\tdelta_amount NUMERIC(24, 10) NOT NULL, \n\treason TEXT NOT NULL, \n\tactor_id BIGINT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (adjustment_id), \n\tCONSTRAINT uq_hf_billing_adjustment_key UNIQUE (event_id, adjustment_key), \n\tCONSTRAINT ck_hf_billing_adjustment_values CHECK (delta_amount<>0 AND length(btrim(reason))>0 AND length(adjustment_key)>0)\n)\n\n"
    )
    op.execute("COMMENT ON TABLE hf_billing_adjustment IS '只追加的计价调整，不覆盖原始金额'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.adjustment_id IS '估值调整ID'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.event_id IS '被调整计价事件ID'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.usage_record_id IS '用量修订依据ID'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.reconciliation_line_id IS '账单差异依据ID'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.adjustment_key IS '调整业务去重键'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.delta_amount IS '有正负号的金额调整，不能为零'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.reason IS '调整原因'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.actor_id IS '人工操作用户ID，系统调整为空'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_billing_adjustment.update_time IS '更新时间'")


def downgrade():
    raise RuntimeError('计价及调整历史不可自动删除，请执行经审核的数据保留方案')

"""预算定义、周期、预占与不可变账本的真实迁移。"""

from alembic import op

revision = '20261027_27'
down_revision = '20261027_26'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_budget (\n\tbudget_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT, \n\tuser_id BIGINT, \n\tpurpose VARCHAR(32) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tcycle_kind VARCHAR(32) NOT NULL, \n\tbusiness_timezone VARCHAR(100) NOT NULL, \n\tactive CHAR(1) DEFAULT 'Y' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (budget_id), \n\tCONSTRAINT ck_hf_budget_subject CHECK ((project_id IS NOT NULL) <> (user_id IS NOT NULL)), \n\tCONSTRAINT ck_hf_budget_state CHECK (purpose IN ('platform','procurement') AND currency ~ '^[A-Z]{3}$' AND cycle_kind IN ('monthly','total') AND active IN ('Y','N') AND revision>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_budget IS '项目或用户预算定义'")
    op.execute("COMMENT ON COLUMN hf_budget.budget_id IS '预算定义ID'")
    op.execute("COMMENT ON COLUMN hf_budget.project_id IS '项目预算主体ID，与用户恰选其一'")
    op.execute("COMMENT ON COLUMN hf_budget.user_id IS '用户预算主体ID，与项目恰选其一'")
    op.execute("COMMENT ON COLUMN hf_budget.purpose IS '预算口径：平台或采购'")
    op.execute("COMMENT ON COLUMN hf_budget.currency IS '预算币种'")
    op.execute("COMMENT ON COLUMN hf_budget.cycle_kind IS '周期类型：自然月或总额'")
    op.execute("COMMENT ON COLUMN hf_budget.business_timezone IS '业务周期时区'")
    op.execute("COMMENT ON COLUMN hf_budget.active IS '是否约束新任务：Y是N否'")
    op.execute("COMMENT ON COLUMN hf_budget.revision IS '定义并发版本'")
    op.execute("COMMENT ON COLUMN hf_budget.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_budget.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_budget.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_budget.update_time IS '更新时间'")
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_budget_project ON hf_budget (project_id, purpose, currency, cycle_kind) WHERE project_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_budget_user ON hf_budget (user_id, purpose, currency, cycle_kind) WHERE user_id IS NOT NULL'
    )
    op.execute(
        "CREATE TABLE hf_budget_period (\n\tperiod_id BIGSERIAL NOT NULL, \n\tbudget_id BIGINT NOT NULL, \n\tperiod_start TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tperiod_end TIMESTAMP(3) WITH TIME ZONE, \n\tlimit_amount NUMERIC(24, 10) NOT NULL, \n\treserved_amount NUMERIC(24, 10) DEFAULT '0' NOT NULL, \n\tconsumed_amount NUMERIC(24, 10) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (period_id), \n\tCONSTRAINT uq_hf_budget_period_start UNIQUE (budget_id, period_start), \n\tCONSTRAINT ck_hf_budget_period_balance CHECK (limit_amount>=0 AND reserved_amount>=0 AND consumed_amount>=0 AND revision>0 AND (period_end IS NULL OR period_end>period_start))\n)"
    )
    op.execute("COMMENT ON TABLE hf_budget_period IS '预算周期与账本余额缓存，允许超额'")
    op.execute("COMMENT ON COLUMN hf_budget_period.period_id IS '预算周期ID'")
    op.execute("COMMENT ON COLUMN hf_budget_period.budget_id IS '所属预算定义ID'")
    op.execute("COMMENT ON COLUMN hf_budget_period.period_start IS '周期起点，含'")
    op.execute("COMMENT ON COLUMN hf_budget_period.period_end IS '周期终点，不含，总额为空'")
    op.execute("COMMENT ON COLUMN hf_budget_period.limit_amount IS '额度缓存，等于额度变动累计'")
    op.execute("COMMENT ON COLUMN hf_budget_period.reserved_amount IS '未结算预占缓存'")
    op.execute("COMMENT ON COLUMN hf_budget_period.consumed_amount IS '已记费用缓存'")
    op.execute("COMMENT ON COLUMN hf_budget_period.revision IS '周期并发版本'")
    op.execute("COMMENT ON COLUMN hf_budget_period.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_budget_period.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_budget_period.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_budget_period.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_budget_reservation (\n\treservation_id BIGSERIAL NOT NULL, \n\tjob_id BIGINT NOT NULL, \n\tperiod_id BIGINT NOT NULL, \n\toriginal_amount NUMERIC(24, 10) NOT NULL, \n\tremaining_amount NUMERIC(24, 10) NOT NULL, \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (reservation_id), \n\tCONSTRAINT uq_hf_budget_reservation_job UNIQUE (job_id, period_id), \n\tCONSTRAINT ck_hf_budget_reservation_balance CHECK (original_amount>=0 AND remaining_amount>=0 AND remaining_amount<=original_amount AND revision>0 AND state IN ('0','1','2','3','4'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_budget_reservation IS '任务在各预算周期的固定预占'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.reservation_id IS '预算预占ID'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.job_id IS '生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.period_id IS '受理时预算周期ID'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.original_amount IS '原始预占金额快照'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.remaining_amount IS '未结算或释放的预占余额'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.state IS '状态：0预占1部分2结清3释放4待确认'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.revision IS '预占并发版本'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_budget_reservation.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_budget_reservation_period ON hf_budget_reservation (period_id, state)')
    op.execute(
        "CREATE TABLE hf_budget_ledger_entry (\n\tentry_id BIGSERIAL NOT NULL, \n\tperiod_id BIGINT NOT NULL, \n\treservation_id BIGINT, \n\tbilling_event_id BIGINT, \n\tadjustment_id BIGINT, \n\tbusiness_event_key VARCHAR(200) NOT NULL, \n\tentry_type VARCHAR(32) NOT NULL, \n\treserved_delta NUMERIC(24, 10) NOT NULL, \n\tconsumed_delta NUMERIC(24, 10) NOT NULL, \n\tlimit_delta NUMERIC(24, 10) DEFAULT '0' NOT NULL, \n\texchange_rate_version_id BIGINT, \n\tconversion_snapshot JSONB DEFAULT '{}'::jsonb NOT NULL, \n\treason TEXT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (entry_id), \n\tCONSTRAINT uq_hf_budget_ledger_event UNIQUE (period_id, business_event_key), \n\tCONSTRAINT ck_hf_budget_ledger_nonzero CHECK (reserved_delta<>0 OR consumed_delta<>0 OR limit_delta<>0), \n\tCONSTRAINT ck_hf_budget_ledger_deltas CHECK ((entry_type='change_limit' AND reserved_delta=0 AND consumed_delta=0) OR (entry_type='reserve' AND reserved_delta>0 AND consumed_delta=0 AND limit_delta=0) OR (entry_type='settle' AND reserved_delta<=0 AND consumed_delta>=0 AND limit_delta=0) OR (entry_type='release' AND reserved_delta<0 AND consumed_delta=0 AND limit_delta=0) OR (entry_type='adjust' AND reserved_delta=0 AND limit_delta=0)), \n\tCONSTRAINT ck_hf_budget_ledger_evidence CHECK ((entry_type<>'settle' OR billing_event_id IS NOT NULL) AND (entry_type<>'adjust' OR adjustment_id IS NOT NULL) AND (entry_type NOT IN ('reserve','release') OR reservation_id IS NOT NULL))\n)"
    )
    op.execute("COMMENT ON TABLE hf_budget_ledger_entry IS '只追加预算变动账本，币种继承周期'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.entry_id IS '账本分录ID'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.period_id IS '预算周期ID'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.reservation_id IS '关联预占ID'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.billing_event_id IS '结算费用事件ID'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.adjustment_id IS '费用调整事件ID'")
    op.execute(
        "COMMENT ON COLUMN hf_budget_ledger_entry.business_event_key IS '周期内唯一业务事件键，不以请求随机值替代'"
    )
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.entry_type IS '额度调整、预占、结算、释放或费用调整'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.reserved_delta IS '有符号预占变动'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.consumed_delta IS '有符号已记费用变动'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.limit_delta IS '有符号额度变动'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.exchange_rate_version_id IS '固定汇率版本ID，同币种为空'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.conversion_snapshot IS '原币种金额、方向及换算舍入快照'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.reason IS '变动依据及说明'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_budget_ledger_entry.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_budget_ledger_period ON hf_budget_ledger_entry (period_id, create_time, entry_id)')


def downgrade():
    op.execute('DROP TABLE hf_budget_ledger_entry')
    op.execute('DROP TABLE hf_budget_reservation')
    op.execute('DROP TABLE hf_budget_period')
    op.execute('DROP TABLE hf_budget')

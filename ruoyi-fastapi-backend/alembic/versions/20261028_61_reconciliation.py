"""真实账单、导入批次及不可变重复冲突证据。"""
from alembic import op
revision = '20261028_61'
down_revision = '20261028_60'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("\nCREATE TABLE hf_reconciliation_batch (\n\tbatch_id BIGSERIAL NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tperiod_start TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tperiod_end TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tsource_file_id BIGINT NOT NULL, \n\tfile_hash CHAR(64) NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (batch_id), \n\tCONSTRAINT uq_hf_reconciliation_file UNIQUE (account_id, period_start, period_end, file_hash), \n\tCONSTRAINT ck_hf_reconciliation_batch CHECK (account_id>0 AND source_file_id>0 AND period_end>period_start AND revision>0 AND status IN ('0','1','2','3') AND file_hash ~ '^[a-f0-9]{64}$')\n)\n\n")
    op.execute('CREATE INDEX ix_hf_reconciliation_account ON hf_reconciliation_batch (account_id, create_time, batch_id)')
    op.execute("COMMENT ON TABLE hf_reconciliation_batch IS '供应商账单导入批次'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.batch_id IS '账单批次ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.account_id IS '供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.period_start IS '账期起点，含'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.period_end IS '账期终点，不含'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.source_file_id IS '持久账单文件ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.file_hash IS '原始账单文件SHA256摘要'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.status IS '0已导入1匹配中2已确认3有差异'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.revision IS '批次并发版本，行状态变化同步递增'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.update_time IS '更新时间'")
    op.execute("\nCREATE TABLE hf_reconciliation_line (\n\tline_id BIGSERIAL NOT NULL, \n\tbatch_id BIGINT NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tline_no INTEGER NOT NULL, \n\texternal_line_key VARCHAR(255) NOT NULL, \n\tsubject_id BIGINT, \n\tcurrency VARCHAR(3) NOT NULL, \n\tamount NUMERIC(24, 10) NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\traw_line JSONB NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (line_id), \n\tCONSTRAINT uq_hf_reconciliation_line_no UNIQUE (batch_id, line_no), \n\tCONSTRAINT uq_hf_reconciliation_external UNIQUE (account_id, external_line_key), \n\tCONSTRAINT ck_hf_reconciliation_line CHECK (batch_id>0 AND account_id>0 AND line_no>0 AND revision>0 AND length(btrim(external_line_key))>0 AND currency ~ '^[A-Z]{3}$' AND status IN ('0','1','2','3') AND (subject_id IS NULL OR subject_id>0) AND (status NOT IN ('1','2') OR subject_id IS NOT NULL) AND amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)), \n\tCONSTRAINT ck_hf_reconciliation_raw CHECK (jsonb_typeof(raw_line)='object')\n)\n\n")
    op.execute('CREATE INDEX ix_hf_reconciliation_line_batch ON hf_reconciliation_line (batch_id, status, line_id)')
    op.execute("COMMENT ON TABLE hf_reconciliation_line IS '供应商真实账单明细，原始金额不可变'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.line_id IS '账单明细ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.batch_id IS '首次记录本账单项的批次ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.account_id IS '供应商账号ID，服务层校验与批次一致'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.line_no IS '原始文件中的起始行号'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.external_line_key IS '供应商账单项稳定身份，保留前导零'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.subject_id IS '已匹配计费对象ID，未匹配为空'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.currency IS '账单原始币种'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.amount IS '账单原始金额，允许负数退款'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.status IS '0未匹配1已匹配2已确认3有差异'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.raw_line IS '白名单原始行证据'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.revision IS '明细并发版本'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.update_time IS '更新时间'")
    op.execute("\nCREATE TABLE hf_reconciliation_observation (\n\tobservation_id BIGSERIAL NOT NULL, \n\tbatch_id BIGINT NOT NULL, \n\tline_no INTEGER NOT NULL, \n\tcanonical_line_id BIGINT NOT NULL, \n\toutcome VARCHAR(16) NOT NULL, \n\traw_line JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (observation_id), \n\tCONSTRAINT uq_hf_reconciliation_observation UNIQUE (batch_id, line_no), \n\tCONSTRAINT ck_hf_reconciliation_observation CHECK (batch_id>0 AND line_no>0 AND canonical_line_id>0 AND outcome IN ('original','duplicate','conflict') AND jsonb_typeof(raw_line)='object')\n)\n\n")
    op.execute('CREATE INDEX ix_hf_reconciliation_observation_line ON hf_reconciliation_observation (canonical_line_id, batch_id)')
    op.execute("COMMENT ON TABLE hf_reconciliation_observation IS '每次账单导入的不可变行证据，重复及冲突不丢失'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.observation_id IS '账单导入观察ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.batch_id IS '本次导入批次ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.line_no IS '本次原始文件起始行号'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.canonical_line_id IS '账号范围唯一账单项ID'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.outcome IS '原始记录、重复证据或金额币种冲突'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.raw_line IS '本次导入白名单原始行，冲突时也保留原值'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_observation.update_time IS '更新时间'")


def downgrade():
    raise RuntimeError("账单事实及导入证据不可自动删除，请执行经审核的数据保留方案")

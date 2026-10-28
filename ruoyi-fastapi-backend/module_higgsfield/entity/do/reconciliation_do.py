"""账单原始金额与导入观察证据，不覆盖计价事件。"""
from sqlalchemy import BigInteger, Column, String, Numeric, Integer, CHAR, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfReconciliationBatch(ContentRecord):
    __tablename__ = 'hf_reconciliation_batch'
    __table_args__ = (
        UniqueConstraint('account_id', 'period_start', 'period_end', 'file_hash', name='uq_hf_reconciliation_file'),
        CheckConstraint("account_id>0 AND source_file_id>0 AND period_end>period_start AND revision>0 "
            "AND status IN ('0','1','2','3') AND file_hash ~ '^[a-f0-9]{64}$'", name='ck_hf_reconciliation_batch'),
        CheckConstraint("import_error IS NULL OR (status='3' AND jsonb_typeof(import_error)='object')",
            name='ck_hf_reconciliation_import_error'),
        Index('ix_hf_reconciliation_account', 'account_id', 'create_time', 'batch_id'),
        {'comment': '供应商账单导入批次', 'info': {'migration_managed': True}},
    )
    batch_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='账单批次ID')
    account_id = Column(BigInteger, nullable=False, comment='供应商账号ID')
    period_start = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='账期起点，含')
    period_end = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='账期终点，不含')
    source_file_id = Column(BigInteger, nullable=False, comment='持久账单文件ID')
    file_hash = Column(CHAR(64), nullable=False, comment='原始账单文件SHA256摘要')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='0已导入1匹配中2已确认3有差异')
    import_error = Column(JSONB, comment='文件解析失败白名单诊断，非失败为空')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='批次并发版本，行状态变化同步递增')


class HfReconciliationLine(ContentRecord):
    __tablename__ = 'hf_reconciliation_line'
    __table_args__ = (
        UniqueConstraint('batch_id', 'line_no', name='uq_hf_reconciliation_line_no'),
        UniqueConstraint('account_id', 'external_line_key', name='uq_hf_reconciliation_external'),
        CheckConstraint("batch_id>0 AND account_id>0 AND line_no>0 AND revision>0 AND length(btrim(external_line_key))>0 "
            "AND currency ~ '^[A-Z]{3}$' AND status IN ('0','1','2','3') "
            "AND (subject_id IS NULL OR subject_id>0) AND (status NOT IN ('1','2') OR subject_id IS NOT NULL) "
            "AND amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)", name='ck_hf_reconciliation_line'),
        CheckConstraint("jsonb_typeof(raw_line)='object'", name='ck_hf_reconciliation_raw'),
        CheckConstraint("(accepted_observation_id IS NULL AND accepted_currency IS NULL AND accepted_amount IS NULL) "
            "OR (accepted_observation_id IS NOT NULL AND accepted_observation_id>0 "
            "AND accepted_currency IS NOT NULL AND accepted_currency ~ '^[A-Z]{3}$' "
            "AND accepted_amount IS NOT NULL AND accepted_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric))",
            name='ck_hf_reconciliation_accepted'),
        Index('ix_hf_reconciliation_line_batch', 'batch_id', 'status', 'line_id'),
        {'comment': '供应商真实账单明细，原始金额不可变', 'info': {'migration_managed': True}},
    )
    line_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='账单明细ID')
    batch_id = Column(BigInteger, nullable=False, comment='首次记录本账单项的批次ID')
    account_id = Column(BigInteger, nullable=False, comment='供应商账号ID，服务层校验与批次一致')
    line_no = Column(Integer, nullable=False, comment='原始文件中的起始行号')
    external_line_key = Column(String(255), nullable=False, comment='供应商账单项稳定身份，保留前导零')
    subject_id = Column(BigInteger, comment='已匹配计费对象ID，未匹配为空')
    currency = Column(String(3), nullable=False, comment='账单原始币种')
    amount = Column(Numeric(24, 10), nullable=False, comment='账单原始金额，允许负数退款')
    accepted_observation_id = Column(BigInteger, comment='人工解决差异采用的导入观察ID，历史选择保留在审计中')
    accepted_currency = Column(String(3), comment='所采用观察的币种，不覆盖首次原始币种')
    accepted_amount = Column(Numeric(24, 10), comment='所采用观察的金额，不覆盖首次原始金额')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='0未匹配1已匹配2已确认3有差异')
    raw_line = Column(JSONB, nullable=False, comment='白名单原始行证据')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='明细并发版本')


class HfReconciliationObservation(ContentRecord):
    __tablename__ = 'hf_reconciliation_observation'
    __table_args__ = (
        UniqueConstraint('batch_id', 'line_no', name='uq_hf_reconciliation_observation'),
        CheckConstraint("batch_id>0 AND line_no>0 AND canonical_line_id>0 "
            "AND outcome IN ('original','duplicate','conflict') AND jsonb_typeof(raw_line)='object'",
            name='ck_hf_reconciliation_observation'),
        Index('ix_hf_reconciliation_observation_line', 'canonical_line_id', 'batch_id'),
        {'comment': '每次账单导入的不可变行证据，重复及冲突不丢失', 'info': {'migration_managed': True}},
    )
    observation_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='账单导入观察ID')
    batch_id = Column(BigInteger, nullable=False, comment='本次导入批次ID')
    line_no = Column(Integer, nullable=False, comment='本次原始文件起始行号')
    canonical_line_id = Column(BigInteger, nullable=False, comment='账号范围唯一账单项ID')
    outcome = Column(String(16), nullable=False, comment='原始记录、重复证据或金额币种冲突')
    raw_line = Column(JSONB, nullable=False, comment='本次导入白名单原始行，冲突时也保留原值')

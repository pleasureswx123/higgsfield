"""预算定义、周期缓存、任务预占和只追加账本。"""

from sqlalchemy import BigInteger, Column, String, Numeric, Text, CHAR, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfBudget(ContentRecord):
    __tablename__ = 'hf_budget'
    __table_args__ = (
        CheckConstraint('(project_id IS NOT NULL) <> (user_id IS NOT NULL)', name='ck_hf_budget_subject'),
        CheckConstraint(
            "purpose IN ('platform','procurement') AND currency ~ '^[A-Z]{3}$' AND cycle_kind IN ('monthly','total') AND active IN ('Y','N') AND revision>0",
            name='ck_hf_budget_state',
        ),
        Index(
            'uq_hf_budget_project',
            'project_id',
            'purpose',
            'currency',
            'cycle_kind',
            unique=True,
            postgresql_where=text('project_id IS NOT NULL'),
        ),
        Index(
            'uq_hf_budget_user',
            'user_id',
            'purpose',
            'currency',
            'cycle_kind',
            unique=True,
            postgresql_where=text('user_id IS NOT NULL'),
        ),
        {'comment': '项目或用户预算定义', 'info': {'migration_managed': True}},
    )
    budget_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='预算定义ID')
    project_id = Column(BigInteger, comment='项目预算主体ID，与用户恰选其一')
    user_id = Column(BigInteger, comment='用户预算主体ID，与项目恰选其一')
    purpose = Column(String(32), nullable=False, comment='预算口径：平台或采购')
    currency = Column(String(3), nullable=False, comment='预算币种')
    cycle_kind = Column(String(32), nullable=False, comment='周期类型：自然月或总额')
    business_timezone = Column(String(100), nullable=False, comment='业务周期时区')
    active = Column(CHAR(1), nullable=False, server_default='Y', comment='是否约束新任务：Y是N否')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='定义并发版本')


class HfBudgetPeriod(ContentRecord):
    __tablename__ = 'hf_budget_period'
    __table_args__ = (
        UniqueConstraint('budget_id', 'period_start', name='uq_hf_budget_period_start'),
        CheckConstraint(
            'limit_amount>=0 AND reserved_amount>=0 AND consumed_amount>=0 AND revision>0 AND (period_end IS NULL OR period_end>period_start)',
            name='ck_hf_budget_period_balance',
        ),
        {'comment': '预算周期与账本余额缓存，允许超额', 'info': {'migration_managed': True}},
    )
    period_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='预算周期ID')
    budget_id = Column(BigInteger, nullable=False, comment='所属预算定义ID')
    period_start = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='周期起点，含')
    period_end = Column(TIMESTAMP(timezone=True, precision=3), comment='周期终点，不含，总额为空')
    limit_amount = Column(Numeric(24, 10), nullable=False, comment='额度缓存，等于额度变动累计')
    reserved_amount = Column(Numeric(24, 10), nullable=False, server_default='0', comment='未结算预占缓存')
    consumed_amount = Column(Numeric(24, 10), nullable=False, server_default='0', comment='已记费用缓存')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='周期并发版本')


class HfBudgetReservation(ContentRecord):
    __tablename__ = 'hf_budget_reservation'
    __table_args__ = (
        UniqueConstraint('job_id', 'period_id', name='uq_hf_budget_reservation_job'),
        CheckConstraint(
            "original_amount>=0 AND remaining_amount>=0 AND remaining_amount<=original_amount AND revision>0 AND state IN ('0','1','2','3','4')",
            name='ck_hf_budget_reservation_balance',
        ),
        Index('ix_hf_budget_reservation_period', 'period_id', 'state'),
        {'comment': '任务在各预算周期的固定预占', 'info': {'migration_managed': True}},
    )
    reservation_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='预算预占ID')
    job_id = Column(BigInteger, nullable=False, comment='生成任务ID')
    period_id = Column(BigInteger, nullable=False, comment='受理时预算周期ID')
    original_amount = Column(Numeric(24, 10), nullable=False, comment='原始预占金额快照')
    remaining_amount = Column(Numeric(24, 10), nullable=False, comment='未结算或释放的预占余额')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0预占1部分2结清3释放4待确认')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='预占并发版本')


class HfBudgetLedgerEntry(ContentRecord):
    __tablename__ = 'hf_budget_ledger_entry'
    __table_args__ = (
        UniqueConstraint('period_id', 'business_event_key', name='uq_hf_budget_ledger_event'),
        CheckConstraint('reserved_delta<>0 OR consumed_delta<>0 OR limit_delta<>0', name='ck_hf_budget_ledger_nonzero'),
        CheckConstraint(
            "(entry_type='change_limit' AND reserved_delta=0 AND consumed_delta=0) OR (entry_type='reserve' AND reserved_delta>0 AND consumed_delta=0 AND limit_delta=0) OR (entry_type='settle' AND reserved_delta<=0 AND consumed_delta>=0 AND limit_delta=0) OR (entry_type='release' AND reserved_delta<0 AND consumed_delta=0 AND limit_delta=0) OR (entry_type='adjust' AND reserved_delta=0 AND limit_delta=0)",
            name='ck_hf_budget_ledger_deltas',
        ),
        CheckConstraint(
            "(entry_type<>'settle' OR billing_event_id IS NOT NULL) AND (entry_type<>'adjust' OR adjustment_id IS NOT NULL) AND (entry_type NOT IN ('reserve','release') OR reservation_id IS NOT NULL)",
            name='ck_hf_budget_ledger_evidence',
        ),
        Index('ix_hf_budget_ledger_period', 'period_id', 'create_time', 'entry_id'),
        {'comment': '只追加预算变动账本，币种继承周期', 'info': {'migration_managed': True}},
    )
    entry_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='账本分录ID')
    period_id = Column(BigInteger, nullable=False, comment='预算周期ID')
    reservation_id = Column(BigInteger, comment='关联预占ID')
    billing_event_id = Column(BigInteger, comment='结算费用事件ID')
    adjustment_id = Column(BigInteger, comment='费用调整事件ID')
    business_event_key = Column(String(200), nullable=False, comment='周期内唯一业务事件键，不以请求随机值替代')
    entry_type = Column(String(32), nullable=False, comment='额度调整、预占、结算、释放或费用调整')
    reserved_delta = Column(Numeric(24, 10), nullable=False, comment='有符号预占变动')
    consumed_delta = Column(Numeric(24, 10), nullable=False, comment='有符号已记费用变动')
    limit_delta = Column(Numeric(24, 10), nullable=False, server_default='0', comment='有符号额度变动')
    exchange_rate_version_id = Column(BigInteger, comment='固定汇率版本ID，同币种为空')
    conversion_snapshot = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='原币种金额、方向及换算舍入快照'
    )
    reason = Column(Text, nullable=False, comment='变动依据及说明')

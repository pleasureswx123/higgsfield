"""分口径计价事实、不可变明细与有符号调整。"""

from sqlalchemy import BigInteger, Column, String, Numeric, Text, CHAR, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfBillingEvent(ContentRecord):
    __tablename__ = 'hf_billing_event'
    __table_args__ = (
        UniqueConstraint('subject_id', 'purpose', name='uq_hf_billing_event_purpose'),
        CheckConstraint(
            "purpose IN ('platform','procurement') AND currency ~ '^[A-Z]{3}$' AND state IN ('0','1','2','3') AND revision>0",
            name='ck_hf_billing_event_state',
        ),
        CheckConstraint(
            "(amount IS NULL OR amount>=0) AND (state NOT IN ('1','2') OR amount IS NOT NULL)",
            name='ck_hf_billing_event_amount',
        ),
        {'comment': '分口径计价结果，不同口径不代表重复消费', 'info': {'migration_managed': True}},
    )
    event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='计价事件ID')
    subject_id = Column(BigInteger, nullable=False, comment='上游计费对象ID')
    usage_record_id = Column(BigInteger, comment='采用的用量修订ID，未知为空')
    purpose = Column(String(32), nullable=False, comment='计价口径：platform平台procurement采购')
    price_version_id = Column(BigInteger, nullable=False, comment='固定价格版本ID')
    currency = Column(String(3), nullable=False, comment='计价原币种')
    amount = Column(Numeric(24, 10), comment='首次确定的金额，未知为空')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='计价状态：0待定1已计算2已确认3有争议')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='计价并发版本')


class HfBillingLineItem(ContentRecord):
    __tablename__ = 'hf_billing_line_item'
    __table_args__ = (
        UniqueConstraint('event_id', 'rule_item_id', name='uq_hf_billing_line_rule'),
        CheckConstraint(
            'quantity>=0 AND unit_quantity>0 AND unit_price>=0 AND amount>=0', name='ck_hf_billing_line_values'
        ),
        CheckConstraint("jsonb_typeof(calculation_snapshot)='object'", name='ck_hf_billing_line_snapshot'),
        {'comment': '不可变计价分项证据', 'info': {'migration_managed': True}},
    )
    line_item_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='计价明细ID')
    event_id = Column(BigInteger, nullable=False, comment='计价事件ID')
    rule_item_id = Column(BigInteger, nullable=False, comment='命中价格分项ID')
    quantity = Column(Numeric(24, 6), nullable=False, comment='参与计价的用量')
    unit_quantity = Column(Numeric(18, 6), nullable=False, comment='计价基数快照')
    unit_price = Column(Numeric(24, 10), nullable=False, comment='单价快照')
    amount = Column(Numeric(24, 10), nullable=False, comment='分项金额')
    calculation_snapshot = Column(JSONB, nullable=False, comment='计算公式及舍入证据快照')


class HfBillingAdjustment(ContentRecord):
    __tablename__ = 'hf_billing_adjustment'
    __table_args__ = (
        UniqueConstraint('event_id', 'adjustment_key', name='uq_hf_billing_adjustment_key'),
        CheckConstraint(
            'delta_amount<>0 AND length(btrim(reason))>0 AND length(adjustment_key)>0',
            name='ck_hf_billing_adjustment_values',
        ),
        {'comment': '只追加的计价调整，不覆盖原始金额', 'info': {'migration_managed': True}},
    )
    adjustment_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='估值调整ID')
    event_id = Column(BigInteger, nullable=False, comment='被调整计价事件ID')
    usage_record_id = Column(BigInteger, comment='用量修订依据ID')
    reconciliation_line_id = Column(BigInteger, comment='账单差异依据ID')
    adjustment_key = Column(String(200), nullable=False, comment='调整业务去重键')
    delta_amount = Column(Numeric(24, 10), nullable=False, comment='有正负号的金额调整，不能为零')
    reason = Column(Text, nullable=False, comment='调整原因')
    actor_id = Column(BigInteger, comment='人工操作用户ID，系统调整为空')

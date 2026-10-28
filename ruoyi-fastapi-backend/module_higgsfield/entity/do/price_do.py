"""价格簿、价格内容与累计阶梯；不提供历史价格删除入口。"""

from sqlalchemy import (
    BigInteger,
    Column,
    String,
    Integer,
    Numeric,
    Text,
    CHAR,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from module_higgsfield.entity.do.asset_do import ContentRecord
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB


class HfPriceActivation(ContentRecord):
    __tablename__ = 'hf_price_activation'
    __table_args__ = (
        CheckConstraint(
            'revision>0 AND (effective_until IS NULL OR effective_until>effective_from)',
            name='ck_hf_price_activation_range',
        ),
        Index('ix_hf_price_activation_book', 'price_book_id', 'effective_from'),
        {'comment': '价格版本生效区间，左闭右开', 'info': {'migration_managed': True}},
    )
    activation_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='价格生效区间ID')
    price_book_id = Column(BigInteger, nullable=False, comment='所属价格簿ID')
    price_version_id = Column(BigInteger, nullable=False, comment='已发布价格版本ID')
    effective_from = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='生效起点，含')
    effective_until = Column(TIMESTAMP(timezone=True, precision=3), comment='生效终点，不含，空为无穷')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='区间并发版本')


class HfPricePublishEvent(ContentRecord):
    __tablename__ = 'hf_price_publish_event'
    __table_args__ = (
        CheckConstraint(
            "action IN ('publish','reschedule','end_activation') AND length(btrim(reason))>0",
            name='ck_hf_price_publish_event',
        ),
        Index('ix_hf_price_publish_event_version', 'price_version_id', 'create_time'),
        {'comment': '只追加价格发布及区间变更历史', 'info': {'migration_managed': True}},
    )
    publish_event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='发布事件ID')
    price_version_id = Column(BigInteger, nullable=False, comment='操作价格版本ID')
    activation_id = Column(BigInteger, nullable=False, comment='操作生效区间ID')
    actor_id = Column(BigInteger, nullable=False, comment='操作用户ID')
    action = Column(String(32), nullable=False, comment='发布、重新安排或结束区间')
    reason = Column(Text, nullable=False, comment='操作依据和原因')
    diff = Column(JSONB, nullable=False, comment='操作前后差异快照')


class HfPriceSource(ContentRecord):
    __tablename__ = 'hf_price_source'
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('vendor_document','official_screenshot','manual_confirmation') AND length(btrim(excerpt))>0",
            name='ck_hf_price_source_type',
        ),
        Index('ix_hf_price_source_observed', 'source_type', 'observed_time'),
        {'comment': '不可变价格来源证据', 'info': {'migration_managed': True}},
    )
    source_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='价格来源ID')
    source_type = Column(String(32), nullable=False, comment='供应商文档、官方截图或人工确认')
    source_url = Column(Text, comment='来源出处地址，不自动抓取')
    excerpt = Column(Text, nullable=False, comment='原文摘录及确认依据')
    file_id = Column(BigInteger, comment='管理受控证据附件ID')
    observed_time = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='证据获取时间')
    create_user_id = Column(BigInteger, nullable=False, comment='证据录入用户ID')


class HfPriceVersionSource(ContentRecord):
    __tablename__ = 'hf_price_version_source'
    __table_args__ = (
        UniqueConstraint('price_version_id', 'source_id', name='uq_hf_price_version_source'),
        {'comment': '价格版本与来源证据关联', 'info': {'migration_managed': True}},
    )
    version_source_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='版本来源关联ID')
    price_version_id = Column(BigInteger, nullable=False, comment='价格版本ID')
    source_id = Column(BigInteger, nullable=False, comment='价格来源证据ID')


class HfPriceBook(ContentRecord):
    __tablename__ = 'hf_price_book'
    __table_args__ = (
        CheckConstraint(
            "(purpose='platform' AND account_id IS NULL) OR (purpose='procurement' AND account_id IS NOT NULL)",
            name='ck_hf_price_book_scope',
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name='ck_hf_price_book_currency'),
        Index(
            'uq_hf_price_book_platform',
            'model_variant_id',
            'purpose',
            'currency',
            unique=True,
            postgresql_where=text('account_id IS NULL'),
        ),
        Index(
            'uq_hf_price_book_account',
            'model_variant_id',
            'purpose',
            'currency',
            'account_id',
            unique=True,
            postgresql_where=text('account_id IS NOT NULL'),
        ),
        {'comment': '价格用途与账号作用域', 'info': {'migration_managed': True}},
    )
    price_book_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='价格簿ID')
    model_variant_id = Column(BigInteger, nullable=False, comment='完整模型规格ID')
    purpose = Column(String(32), nullable=False, comment='价格用途：platform平台价或procurement采购价')
    account_id = Column(BigInteger, comment='采购账号ID，平台价为空')
    currency = Column(String(3), nullable=False, comment='计价币种代码')
    price_book_name = Column(String(200), nullable=False, comment='价格簿名称')


class HfPriceVersion(ContentRecord):
    __tablename__ = 'hf_price_version'
    __table_args__ = (
        UniqueConstraint('price_book_id', 'version_no', name='uq_hf_price_version_no'),
        UniqueConstraint('price_book_id', 'price_version_id', name='uq_hf_price_version_identity'),
        CheckConstraint(
            "version_no>0 AND revision>0 AND schema_version=1 AND status IN ('0','1') AND rounding_mode='half_up' AND calculation_scale BETWEEN 0 AND 10",
            name='ck_hf_price_version_state',
        ),
        {'comment': '价格版本内容，发布后不可修改', 'info': {'migration_managed': True}},
    )
    price_version_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='价格版本ID')
    price_book_id = Column(BigInteger, nullable=False, comment='所属价格簿ID')
    version_no = Column(Integer, nullable=False, comment='价格簿内版本号')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1已发布')
    rounding_mode = Column(String(32), nullable=False, comment='舍入方式：half_up')
    calculation_scale = Column(Integer, nullable=False, comment='显式指定计算保留位数，0到10')
    schema_version = Column(Integer, nullable=False, server_default='1', comment='价格模板结构版本')
    create_user_id = Column(BigInteger, nullable=False, comment='价格编辑者用户ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='草稿并发版本')


class HfPriceRuleItem(ContentRecord):
    __tablename__ = 'hf_price_rule_item'
    __table_args__ = (
        UniqueConstraint('price_version_id', 'item_code', 'quantity_from', name='uq_hf_price_item_start'),
        CheckConstraint(
            'unit_quantity>0 AND unit_price>=0 AND quantity_from>=0 AND (quantity_to IS NULL OR quantity_to>quantity_from)',
            name='ck_hf_price_item_numbers',
        ),
        CheckConstraint(
            'unit_price>0 OR (free_reason IS NOT NULL AND length(btrim(free_reason))>0)',
            name='ck_hf_price_item_free_reason',
        ),
        CheckConstraint(
            "unit IN ('token','image','second','character') AND formula_template IN ('linear','tiered')",
            name='ck_hf_price_item_template',
        ),
        {'comment': '价格计费分项及累计阶梯', 'info': {'migration_managed': True}},
    )
    item_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='价格分项ID')
    price_version_id = Column(BigInteger, nullable=False, comment='所属价格版本ID')
    item_code = Column(String(100), nullable=False, comment='计费用量分项代码')
    unit = Column(String(32), nullable=False, comment='用量单位')
    unit_quantity = Column(Numeric(18, 6), nullable=False, comment='单价对应的数量基数')
    unit_price = Column(Numeric(24, 10), nullable=False, comment='基数对应单价，零价需说明')
    quantity_from = Column(Numeric(24, 6), nullable=False, server_default='0', comment='累计阶梯下限，含')
    quantity_to = Column(Numeric(24, 6), comment='累计阶梯上限，不含，空为无穷')
    formula_template = Column(String(100), nullable=False, comment='受控公式模板键')
    free_reason = Column(Text, comment='明确免费依据')

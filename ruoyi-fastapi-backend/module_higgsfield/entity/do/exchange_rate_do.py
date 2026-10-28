"""带来源与有效期的不可变汇率版本。"""

from sqlalchemy import BigInteger, Column, String, Numeric, CHAR, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfExchangeRateVersion(ContentRecord):
    __tablename__ = 'hf_exchange_rate_version'
    __table_args__ = (
        CheckConstraint(
            "base_currency ~ '^[A-Z]{3}$' AND quote_currency ~ '^[A-Z]{3}$' AND base_currency<>quote_currency AND rate>0 AND revision>0 AND status IN ('0','1') AND (valid_until IS NULL OR valid_until>valid_from)",
            name='ck_hf_exchange_rate_version',
        ),
        Index('ix_hf_exchange_rate_pair', 'base_currency', 'quote_currency', 'status', 'valid_from'),
        {'comment': '汇率版本及历史适用区间', 'info': {'migration_managed': True}},
    )
    exchange_rate_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='汇率版本ID')
    base_currency = Column(String(3), nullable=False, comment='基础币种')
    quote_currency = Column(String(3), nullable=False, comment='计价币种')
    rate = Column(Numeric(24, 12), nullable=False, comment='一单位基础币兑换计价币的数量')
    valid_from = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='有效起点，含')
    valid_until = Column(TIMESTAMP(timezone=True, precision=3), comment='有效终点，不含，空为无穷')
    source_id = Column(BigInteger, nullable=False, comment='来源证据ID')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1已发布')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')

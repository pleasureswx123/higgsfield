"""管理消费归属独立于业务项目，不开放删除。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, String, UniqueConstraint
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfCostCenter(ContentRecord):
    __tablename__ = 'hf_cost_center'
    __table_args__ = (
        UniqueConstraint('code', name='uq_hf_cost_center_code'),
        CheckConstraint("active IN ('Y','N')", name='ck_hf_cost_center_active'),
        {'comment': '管理测试等非项目消费归属', 'info': {'migration_managed': True}},
    )
    cost_center_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='成本中心ID')
    code = Column(String(100), nullable=False, comment='成本中心唯一编码')
    cost_center_name = Column(String(200), nullable=False, comment='成本中心名称')
    active = Column(CHAR(1), nullable=False, server_default='Y', comment='是否允许新消费：Y是N否')

"""派生关系与处理状态，原文件和已完成派生文件保持不可变。"""
from sqlalchemy import BigInteger, CHAR, Column, Integer, String, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfMediaDerivative(ContentRecord):
    __tablename__ = 'hf_media_derivative'
    __table_args__ = (
        UniqueConstraint('source_file_id', 'recipe', name='uq_hf_derivative_source_recipe'),
        UniqueConstraint('derived_file_id', name='uq_hf_derivative_file'),
        CheckConstraint("state IN ('0','1','2','3','4')", name='ck_hf_derivative_state'),
        CheckConstraint('source_file_id>0 AND revision>0 AND attempts>=0 AND '
                        '(derived_file_id IS NULL OR (derived_file_id>0 AND derived_file_id<>source_file_id))',
                        name='ck_hf_derivative_identity'),
        CheckConstraint("(state='2')=(derived_file_id IS NOT NULL)", name='ck_hf_derivative_ready'),
        CheckConstraint("(state='1' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
                        "(state<>'1' AND lease_owner IS NULL AND lease_until IS NULL)", name='ck_hf_derivative_lease'),
        Index('ix_hf_derivative_due', 'state', 'next_action_time', 'derivative_id'),
        {'comment': '媒体派生文件关系与处理租约，不开放业务删除', 'info': {'migration_managed': True}},
    )
    derivative_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='派生任务ID')
    source_file_id = Column(BigInteger, nullable=False, comment='不可变原文件ID')
    recipe = Column(String(64), nullable=False, comment='派生配方版本')
    derived_file_id = Column(BigInteger, comment='已登记的派生文件ID')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='0等待1处理中2就绪3待重试4终止失败')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='领取及写回并发栅栏')
    lease_owner = Column(String(100), comment='工作器身份')
    lease_until = Column(TIMESTAMP(timezone=True), comment='领取截止时间')
    attempts = Column(Integer, nullable=False, server_default='0', comment='累计领取次数')
    next_action_time = Column(TIMESTAMP(timezone=True), nullable=False, comment='下一次可处理时间')
    error_code = Column(String(64), comment='白名单错误码')

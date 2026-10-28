"""事务消息及消费者完成去重，不将消息载荷作为业务事实源。"""

from sqlalchemy import BigInteger, Column, String, Integer, CHAR, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfTaskEvent(ContentRecord):
    __tablename__ = 'hf_task_event'
    __table_args__ = (
        UniqueConstraint('job_id', 'sequence', name='uq_hf_task_event_sequence'),
        CheckConstraint(
            "sequence>0 AND schema_version>0 AND event_type IN ('task.state','output.state','chat.delta','chat.completed','usage.updated','task.problem')",
            name='ck_hf_task_event_contract',
        ),
        Index('ix_hf_task_event_occurred', 'occurred_time'),
        {'comment': '可重放持久任务事件，序号按任务事务分配', 'info': {'migration_managed': True}},
    )
    event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='任务事件ID')
    job_id = Column(BigInteger, nullable=False, comment='所属生成任务ID')
    sequence = Column(BigInteger, nullable=False, comment='任务内提交事件序号，从一开始')
    event_type = Column(String(32), nullable=False, comment='持久事件类别，不包含连接级消息')
    schema_version = Column(Integer, nullable=False, server_default='1', comment='事件载荷结构版本')
    payload = Column(JSONB, nullable=False, comment='受控事件事实，不含秘密或临时签名地址')
    occurred_time = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='事实发生时间，不作为排序键')


class HfOutboxEvent(ContentRecord):
    __tablename__ = 'hf_outbox_event'
    __table_args__ = (
        CheckConstraint(
            "state IN ('0','1') AND attempt_count>=0 AND ((state='0' AND published_time IS NULL) OR (state='1' AND published_time IS NOT NULL))",
            name='ck_hf_outbox_state',
        ),
        Index('ix_hf_outbox_pending', 'next_attempt_time', 'event_id', postgresql_where=text("state='0'")),
        {'comment': '与业务写入同事务的待投递事件', 'info': {'migration_managed': True}},
    )
    event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='事务事件唯一ID')
    event_type = Column(String(100), nullable=False, comment='事件类型')
    aggregate_type = Column(String(100), nullable=False, comment='所属业务聚合类别')
    aggregate_id = Column(BigInteger, nullable=False, comment='所属业务聚合ID')
    payload = Column(JSONB, nullable=False, comment='资源引用及必要非秘密参数')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0待投递1已投递')
    next_attempt_time = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='下次投递时间')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='投递尝试次数')
    published_time = Column(TIMESTAMP(timezone=True, precision=3), comment='成功投递时间')


class HfProcessedEvent(ContentRecord):
    __tablename__ = 'hf_processed_event'
    __table_args__ = (
        UniqueConstraint('consumer_name', 'event_id', name='uq_hf_processed_consumer_event'),
        {'comment': '消费者已完成事件去重，与处理结果同事务', 'info': {'migration_managed': True}},
    )
    processed_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='消费完成记录ID')
    consumer_name = Column(String(100), nullable=False, comment='消费者稳定名称')
    event_id = Column(BigInteger, nullable=False, comment='事务事件ID')
    processed_time = Column(TIMESTAMP(timezone=True, precision=3), nullable=False, comment='处理完成时间')

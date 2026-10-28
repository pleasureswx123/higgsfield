"""协作状态事件不可删除；状态事实保存在目标对象上。"""

from sqlalchemy import BigInteger, CheckConstraint, Column, Index, String, Text
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfReviewEvent(ContentRecord):
    __tablename__ = 'hf_review_event'
    __table_args__ = (
        CheckConstraint('num_nonnulls(element_id,output_id)=1', name='ck_hf_review_target'),
        CheckConstraint(
            "from_status IN ('none','working','review','approved','rejected') AND to_status IN ('none','working','review','approved','rejected') AND from_status != to_status",
            name='ck_hf_review_status',
        ),
        Index('ix_hf_review_element', 'element_id', 'create_time'),
        Index('ix_hf_review_output', 'output_id', 'create_time'),
        {'comment': '内容工作状态变更历史', 'info': {'migration_managed': True}},
    )
    review_event_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='状态事件ID')
    element_id = Column(BigInteger, comment='元素目标ID')
    output_id = Column(BigInteger, comment='生成作品目标ID')
    actor_id = Column(BigInteger, nullable=False, comment='操作者用户ID')
    from_status = Column(String(32), nullable=False, comment='变更前工作状态')
    to_status = Column(String(32), nullable=False, comment='变更后工作状态')
    reason = Column(Text, comment='变更说明')

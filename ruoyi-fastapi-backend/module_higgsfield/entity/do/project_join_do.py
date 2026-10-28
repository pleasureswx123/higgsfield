"""项目加入申请事实，状态变更由审批事务管理。"""
from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, Index, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from common.mixin import AuditTimeMixin
from config.database import Base


class HfProjectJoinRequest(AuditTimeMixin, Base):
    __tablename__ = 'hf_project_join_request'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        CheckConstraint("project_id>0 AND user_id>0 AND revision>0 AND status IN ('0','1','2','3')", name='ck_hf_join_fields'),
        CheckConstraint("reason IS NULL OR char_length(reason)<=5000", name='ck_hf_join_reason'),
        CheckConstraint("(reviewer_id IS NULL AND reviewed_time IS NULL) OR (reviewer_id IS NOT NULL AND reviewer_id>0 AND reviewed_time IS NOT NULL)", name='ck_hf_join_reviewer'),
        CheckConstraint("(status='0' AND reviewer_id IS NULL AND reviewed_time IS NULL) OR (status IN ('1','2') AND reviewer_id IS NOT NULL AND reviewed_time IS NOT NULL) OR status='3'", name='ck_hf_join_review_state'),
        Index('uq_hf_join_pending', 'project_id', 'user_id', unique=True, postgresql_where=text("status='0'")),
        Index('ix_hf_join_project_status_time', 'project_id', 'status', 'create_time', 'request_id'),
        {'comment': '项目加入申请及审批状态', 'info': {'migration_managed': True}},
    )
    request_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='加入申请ID')
    project_id = Column(BigInteger, nullable=False, comment='目标项目ID')
    user_id = Column(BigInteger, nullable=False, comment='申请用户ID')
    status = Column(CHAR(1), nullable=False, server_default=text("'0'"), comment='状态：0待审批1批准2拒绝3取消')
    reason = Column(Text, nullable=True, comment='申请说明')
    reviewer_id = Column(BigInteger, nullable=True, comment='处理用户ID')
    reviewed_time = Column(TIMESTAMP(timezone=True, precision=3), nullable=True, comment='处理时间')
    revision = Column(BigInteger, nullable=False, server_default=text('1'), comment='并发修订号')
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    update_by = Column(String(64), nullable=False, server_default=text("''"), comment='更新者')


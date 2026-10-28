"""不可删除的业务审计事实，与受控变更同事务写入。"""

from sqlalchemy import BigInteger, Column, String, Text, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfAuditLog(ContentRecord):
    __tablename__ = 'hf_audit_log'
    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('user','system') AND (actor_kind<>'user' OR actor_id IS NOT NULL)", name='ck_hf_audit_actor'
        ),
        Index('ix_hf_audit_project', 'project_id', 'create_time', 'audit_id'),
        Index('ix_hf_audit_object', 'object_type', 'object_id', 'create_time'),
        Index('ix_hf_audit_actor', 'actor_id', 'create_time'),
        {'comment': '只追加业务审计记录', 'info': {'migration_managed': True}},
    )
    audit_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='审计记录ID')
    actor_id = Column(BigInteger, comment='操作者用户ID')
    actor_kind = Column(String(32), nullable=False, comment='操作者类别')
    project_id = Column(BigInteger, comment='所属业务项目ID')
    object_type = Column(String(100), nullable=False, comment='审计对象类型')
    object_id = Column(String(255), nullable=False, comment='历史对象定位标识')
    action = Column(String(100), nullable=False, comment='受控操作名称')
    request_id = Column(String(100), nullable=False, comment='关联请求摘要标识')
    before_after = Column(JSONB, nullable=False, comment='操作前后非秘密白名单事实')
    reason = Column(Text, comment='敏感操作原因')

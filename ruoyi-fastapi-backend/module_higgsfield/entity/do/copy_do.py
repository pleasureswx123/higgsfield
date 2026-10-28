"""长期保留受控复制来源，不依赖有期限的幂等响应记录。"""

from sqlalchemy import BigInteger, CheckConstraint, Column, String, UniqueConstraint
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfContentCopy(ContentRecord):
    __tablename__ = 'hf_content_copy'
    __table_args__ = (
        CheckConstraint("target_kind IN ('element','asset')", name='ck_hf_copy_kind'),
        UniqueConstraint('target_kind', 'target_version_id', name='uq_hf_copy_target'),
        {'comment': '受控复制固定版本来源证据', 'info': {'migration_managed': True}},
    )
    copy_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='复制证据ID')
    target_kind = Column(String(16), nullable=False, comment='复制对象类型')
    source_project_id = Column(BigInteger, nullable=False, comment='来源项目ID')
    source_version_id = Column(BigInteger, nullable=False, comment='来源素材版本或元素修订ID')
    target_project_id = Column(BigInteger, nullable=False, comment='目标项目ID')
    target_version_id = Column(BigInteger, nullable=False, comment='目标素材版本或元素修订ID')
    actor_id = Column(BigInteger, nullable=False, comment='复制操作者用户ID')

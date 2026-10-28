"""私有草稿及可替换的结构化引用关系。"""

from sqlalchemy import BigInteger, Column, Integer, String, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfPromptDraft(ContentRecord):
    __tablename__ = 'hf_prompt_draft'
    __table_args__ = (
        UniqueConstraint('draft_id', 'project_id', name='uq_hf_draft_project'),
        CheckConstraint(
            "kind IN ('image','video','chat') AND revision > 0 AND schema_version = 1", name='ck_hf_draft_state'
        ),
        Index('ix_hf_draft_owner', 'owner_id', 'project_id', 'update_time', 'draft_id'),
        {'comment': '本人私有创作草稿', 'info': {'migration_managed': True}},
    )
    draft_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='草稿ID')
    project_id = Column(BigInteger, nullable=False, comment='所属项目ID')
    owner_id = Column(BigInteger, nullable=False, comment='草稿所有者用户ID')
    kind = Column(String(32), nullable=False, comment='创作类型')
    body = Column(JSONB, nullable=False, comment='白名单提示词和参数草稿')
    schema_version = Column(Integer, nullable=False, server_default='1', comment='结构契约版本')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')


class HfDraftReference(ContentRecord):
    __tablename__ = 'hf_draft_reference'
    __table_args__ = (
        UniqueConstraint('draft_id', 'reference_key', 'ordinal', name='uq_hf_draft_reference'),
        CheckConstraint('ordinal >= 0', name='ck_hf_draft_reference_order'),
        Index('ix_hf_draft_reference_order', 'draft_id', 'ordinal'),
        {'comment': '草稿固定媒体引用关系', 'info': {'migration_managed': True}},
    )
    reference_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='引用行主键')
    draft_id = Column(BigInteger, nullable=False, comment='草稿ID')
    reference_key = Column(BigInteger, nullable=False, comment='编辑器提及稳定键')
    asset_version_id = Column(BigInteger, nullable=False, comment='固定素材版本ID')
    element_revision_id = Column(BigInteger, comment='固定元素修订ID')
    media_role = Column(String(32), nullable=False, comment='媒体输入角色')
    ordinal = Column(Integer, nullable=False, comment='用户选择顺序')

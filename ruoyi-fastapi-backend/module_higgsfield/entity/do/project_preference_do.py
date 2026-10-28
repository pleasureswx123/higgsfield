"""个人项目分组与偏好，不参与项目授权。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, Index, Integer, String, Text, UniqueConstraint, text
from common.mixin import AuditTimeMixin
from config.database import Base


class PreferenceAudit(AuditTimeMixin):
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    create_by = Column(String(64), nullable=False, server_default=text("''"), comment='创建者')
    update_by = Column(String(64), nullable=False, server_default=text("''"), comment='更新者')


class HfProjectCollection(PreferenceAudit, Base):
    __tablename__ = 'hf_project_collection'
    __table_args__ = (
        UniqueConstraint('user_id', 'collection_name', name='uq_hf_collection_user_name'),
        CheckConstraint("user_id>0 AND revision>0 AND char_length(btrim(collection_name))>0", name='ck_hf_collection_fields'),
        CheckConstraint("color IS NULL OR color ~ '^#[0-9a-f]{6}$'", name='ck_hf_collection_color'),
        CheckConstraint('description IS NULL OR char_length(description)<=2000', name='ck_hf_collection_description'),
        Index('ix_hf_collection_user_order', 'user_id', 'order_num', 'collection_id'),
        {'comment': '个人项目集合，不授予项目访问权', 'info': {'migration_managed': True}},
    )
    collection_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='集合ID')
    user_id = Column(BigInteger, nullable=False, comment='所属用户ID')
    collection_name = Column(String(200), nullable=False, comment='集合名称')
    description = Column(Text, nullable=True, comment='集合说明')
    color = Column(String(7), nullable=True, comment='个人集合颜色')
    order_num = Column(Integer, nullable=False, server_default=text('0'), comment='个人排序')
    revision = Column(BigInteger, nullable=False, server_default=text('1'), comment='并发修订')


class HfUserProjectPreference(PreferenceAudit, Base):
    __tablename__ = 'hf_user_project_preference'
    __table_args__ = (
        UniqueConstraint('user_id', 'project_id', name='uq_hf_preference_user_project'),
        CheckConstraint("user_id>0 AND project_id>0 AND revision>0 AND (collection_id IS NULL OR collection_id>0) AND is_pinned IN ('Y','N') AND is_hidden IN ('Y','N')", name='ck_hf_project_preference_fields'),
        Index('ix_hf_preference_user_flags_order', 'user_id', 'is_hidden', 'is_pinned', 'order_num'),
        {'comment': '项目个人导航偏好，不改变成员或项目状态', 'info': {'migration_managed': True}},
    )
    preference_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='偏好ID')
    user_id = Column(BigInteger, nullable=False, comment='所属用户ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    collection_id = Column(BigInteger, nullable=True, comment='本人集合ID')
    is_pinned = Column(CHAR(1), nullable=False, server_default=text("'N'"), comment='是否置顶：Y是N否')
    is_hidden = Column(CHAR(1), nullable=False, server_default=text("'N'"), comment='是否隐藏：Y是N否')
    order_num = Column(Integer, nullable=False, server_default=text('0'), comment='个人排序')
    revision = Column(BigInteger, nullable=False, server_default=text('1'), comment='并发修订')

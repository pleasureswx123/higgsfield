from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from common.mixin import AuditTimeMixin
from config.database import Base


class HfFolder(AuditTimeMixin, Base):
    """目录身份与当前层级；目录操作统一锁定所属空间。"""

    __tablename__ = 'hf_folder'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        UniqueConstraint('folder_id', 'space_id', name='uq_hf_folder_space'),
        CheckConstraint('parent_id <> folder_id', name='ck_hf_folder_parent'),
        CheckConstraint('revision > 0', name='ck_hf_folder_revision'),
        CheckConstraint("del_flag IN ('0','2')", name='ck_hf_folder_del'),
        CheckConstraint("folder_kind IN ('media','element')", name='ck_hf_folder_kind'),
        CheckConstraint(
            "color IN ('lime','cyan','slate','violet','purple','pink','yellow')", name='ck_hf_folder_color'
        ),
        Index(
            'uq_hf_folder_root',
            'space_id',
            'normalized_name',
            unique=True,
            postgresql_where=text("parent_id IS NULL AND del_flag='0'"),
        ),
        Index(
            'uq_hf_folder_child',
            'space_id',
            'parent_id',
            'normalized_name',
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL AND del_flag='0'"),
        ),
        {'comment': '空间目录', 'info': {'migration_managed': True}},
    )
    folder_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='目录ID')
    space_id = Column(BigInteger, nullable=False, comment='归属空间ID')
    parent_id = Column(BigInteger, comment='父目录ID，空表示根目录')
    folder_name = Column(String(200), nullable=False, comment='目录显示名称')
    normalized_name = Column(String(200), nullable=False, comment='NFKC规范化并忽略大小写的名称')
    description = Column(Text, nullable=False, server_default='', comment='目录描述')
    color = Column(String(16), nullable=False, server_default='lime', comment='目录颜色')
    folder_kind = Column(String(16), nullable=False, server_default='media', comment='目录类型')
    order_num = Column(Integer, nullable=False, server_default='0', comment='显示顺序')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志：0存在2删除')
    create_by = Column(String(64), nullable=False, server_default='', comment='创建者')
    update_by = Column(String(64), nullable=False, server_default='', comment='更新者')


class HfRecycleEntry(AuditTimeMixin, Base):
    """删除与恢复证据，不提供删除接口。"""

    __tablename__ = 'hf_recycle_entry'
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    __table_args__ = (
        CheckConstraint("target_kind IN ('folder','element','asset','output')", name='ck_hf_recycle_kind'),
        CheckConstraint("state IN ('active','restored','expired')", name='ck_hf_recycle_state'),
        CheckConstraint('restore_until > deleted_time', name='ck_hf_recycle_window'),
        CheckConstraint('revision > 0', name='ck_hf_recycle_revision'),
        Index('uq_hf_recycle_active', 'target_kind', 'target_id', unique=True, postgresql_where=text("state='active'")),
        Index('ix_hf_recycle_project', 'project_id', 'state', 'deleted_time', 'recycle_id'),
        {'comment': '内容回收记录', 'info': {'migration_managed': True}},
    )
    recycle_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='回收记录ID')
    project_id = Column(BigInteger, nullable=False, comment='所属项目ID')
    target_kind = Column(String(16), nullable=False, comment='对象类型')
    target_id = Column(BigInteger, nullable=False, comment='对象稳定ID')
    original_parent_id = Column(BigInteger, comment='原父目录ID')
    deleted_time = Column(TIMESTAMP(timezone=True), nullable=False, comment='删除时间')
    restore_until = Column(TIMESTAMP(timezone=True), nullable=False, comment='自助恢复截止时间')
    actor_id = Column(BigInteger, nullable=False, comment='删除操作者ID')
    state = Column(String(16), nullable=False, server_default='active', comment='回收状态')
    restored_time = Column(TIMESTAMP(timezone=True), comment='恢复时间')
    restored_by = Column(BigInteger, comment='恢复操作者ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')
    snapshot = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='删除前展示快照')
    create_by = Column(String(64), nullable=False, server_default='', comment='创建者')
    update_by = Column(String(64), nullable=False, server_default='', comment='更新者')

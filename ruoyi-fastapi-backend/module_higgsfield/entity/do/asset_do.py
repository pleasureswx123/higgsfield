from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Column,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from common.mixin import AuditTimeMixin
from config.database import Base


class ContentRecord(AuditTimeMixin, Base):
    """内容模块共用若依审计字段；实体各自声明生命周期。"""

    __abstract__ = True
    __create_time_nullable__ = False
    __update_time_nullable__ = False
    create_by = Column(String(64), nullable=False, server_default='', comment='创建者')
    update_by = Column(String(64), nullable=False, server_default='', comment='更新者')


class HfUploadSession(ContentRecord):
    __tablename__ = 'hf_upload_session'
    __table_args__ = (
        CheckConstraint('byte_size > 0 AND part_size > 0 AND part_count > 0', name='ck_hf_upload_sizes'),
        CheckConstraint("state IN ('0','1','2','3','4','5','6')", name='ck_hf_upload_state'),
        CheckConstraint(
            "(purpose IN ('asset','element_import') AND project_id IS NOT NULL) OR "
            "(purpose IN ('price_source','reconciliation') AND project_id IS NULL)",
            name='ck_hf_upload_purpose',
        ),
        CheckConstraint('expires_time > create_time AND revision > 0', name='ck_hf_upload_expiry'),
        CheckConstraint(
            "state != '3' OR (completed_file_id IS NOT NULL AND verified_sha256 IS NOT NULL "
            'AND expected_sha256 IS NOT NULL AND verified_sha256=expected_sha256)',
            name='ck_hf_upload_ready',
        ),
        Index('ix_hf_upload_owner', 'owner_id', 'project_id', 'create_time', 'upload_id'),
        Index('ix_hf_upload_expiry', 'state', 'expires_time'),
        {'comment': '平台上传会话', 'info': {'migration_managed': True}},
    )
    upload_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='上传会话ID')
    owner_id = Column(BigInteger, nullable=False, comment='上传所有者ID')
    project_id = Column(BigInteger, comment='所属项目ID')
    purpose = Column(String(32), nullable=False, comment='上传用途')
    file_name = Column(String(255), nullable=False, comment='展示文件名，不作为存储路径')
    declared_mime_type = Column(String(255), nullable=False, comment='客户端声明类型')
    byte_size = Column(BigInteger, nullable=False, comment='声明总字节数')
    part_size = Column(BigInteger, nullable=False, comment='固定分片大小')
    part_count = Column(Integer, nullable=False, comment='分片数量')
    expected_sha256 = Column(CHAR(64), comment='期望整文件摘要')
    verified_sha256 = Column(CHAR(64), comment='实际整文件摘要')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='0创建1上传2校验3就绪4失败5取消6过期')
    expires_time = Column(TIMESTAMP(timezone=True), nullable=False, comment='未绑定上传有效期')
    completed_file_id = Column(BigInteger, comment='验证完成的文件ID')
    validation_errors = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment='白名单校验错误')
    schema_version = Column(Integer, nullable=False, server_default='1', comment='错误信息格式版本')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='内部并发修订')


class HfUploadPart(ContentRecord):
    __tablename__ = 'hf_upload_part'
    __table_args__ = (
        UniqueConstraint('session_id', 'part_no', name='uq_hf_upload_part'),
        CheckConstraint('part_no > 0 AND byte_offset >= 0 AND byte_size > 0', name='ck_hf_upload_part_size'),
        {'comment': '上传已接收分片', 'info': {'migration_managed': True}},
    )
    part_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='分片ID')
    session_id = Column(BigInteger, nullable=False, comment='上传会话ID')
    part_no = Column(Integer, nullable=False, comment='一开始的分片编号')
    byte_offset = Column(BigInteger, nullable=False, comment='零起点字节偏移')
    byte_size = Column(BigInteger, nullable=False, comment='分片实际字节数')
    sha256 = Column(CHAR(64), nullable=False, comment='分片实际摘要')
    storage_key = Column(Text, nullable=False, comment='内部暂存定位键')


class HfStoredFile(ContentRecord):
    __tablename__ = 'hf_stored_file'
    __table_args__ = (
        UniqueConstraint('storage_key', name='uq_hf_stored_file_key'),
        CheckConstraint(
            'byte_size >= 0 AND (width IS NULL OR width > 0) AND (height IS NULL OR height > 0) '
            'AND (seconds IS NULL OR seconds > 0)',
            name='ck_hf_stored_file_sizes',
        ),
        CheckConstraint("state IN ('0','1','2','3','4')", name='ck_hf_stored_file_state'),
        Index('ix_hf_stored_file_hash', 'sha256', 'byte_size'),
        {'comment': '受控持久文件', 'info': {'migration_managed': True}},
    )
    file_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='文件ID')
    storage_key = Column(Text, nullable=False, comment='服务端生成相对存储键')
    sha256 = Column(CHAR(64), nullable=False, comment='文件内容摘要')
    byte_size = Column(BigInteger, nullable=False, comment='文件字节数')
    mime_type = Column(String(100), nullable=False, comment='经校验实际类型')
    width = Column(Integer, comment='媒体宽度')
    height = Column(Integer, comment='媒体高度')
    seconds = Column(Numeric(18, 6), comment='视频时长秒')
    state = Column(CHAR(1), nullable=False, comment='0暂存1就绪2隔离3丢失4已清理')
    purged_time = Column(TIMESTAMP(timezone=True), comment='物理清理时间证据')


class HfAsset(ContentRecord):
    __tablename__ = 'hf_asset'
    __table_args__ = (
        UniqueConstraint('asset_id', 'space_id', name='uq_hf_asset_space_identity'),
        CheckConstraint('revision > 0', name='ck_hf_asset_revision'),
        CheckConstraint("work_status IN ('none','working','review','approved','rejected')", name='ck_hf_asset_work_status'),
        CheckConstraint("del_flag IN ('0','2')", name='ck_hf_asset_del'),
        CheckConstraint("media_type IN ('image','video','audio','document')", name='ck_hf_asset_media_type'),
        Index('ix_hf_asset_space_time', 'space_id', 'create_time', 'asset_id', postgresql_where=text("del_flag='0'")),
        {'comment': '素材身份', 'info': {'migration_managed': True}},
    )
    asset_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='素材ID')
    space_id = Column(BigInteger, nullable=False, comment='归属空间ID')
    asset_name = Column(String(200), nullable=False, comment='素材名称')
    work_status = Column(String(16), nullable=False, server_default='none', comment='素材工作状态：none无状态、working进行中、review待审核、approved已通过、rejected已驳回')
    media_type = Column(String(32), nullable=False, comment='素材媒体类型')
    create_user_id = Column(BigInteger, nullable=False, comment='作者用户ID')
    current_version_id = Column(BigInteger, comment='当前就绪版本ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发修订')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='0存在2删除')


class HfAssetVersion(ContentRecord):
    __tablename__ = 'hf_asset_version'
    __table_args__ = (
        UniqueConstraint('asset_id', 'version_no', name='uq_hf_asset_version_no'),
        UniqueConstraint('asset_id', 'version_id', name='uq_hf_asset_version_identity'),
        CheckConstraint('version_no > 0', name='ck_hf_asset_version_no'),
        CheckConstraint(
            'source_asset_version_id IS NULL OR source_asset_version_id <> version_id', name='ck_hf_asset_source_self'
        ),
        CheckConstraint('num_nonnulls(source_asset_version_id,source_output_id) <= 1', name='ck_hf_asset_source_one'),
        {'comment': '素材不可变版本', 'info': {'migration_managed': True}},
    )
    version_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='素材版本ID')
    asset_id = Column(BigInteger, nullable=False, comment='所属素材ID')
    version_no = Column(Integer, nullable=False, comment='递增版本号')
    file_id = Column(BigInteger, nullable=False, comment='持久文件ID')
    source_output_id = Column(BigInteger, comment='来源生成作品ID')
    create_user_id = Column(BigInteger, nullable=False, comment='版本创建者ID')
    media_metadata = Column(
        'metadata', JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='媒体分析快照'
    )
    source_asset_version_id = Column(BigInteger, comment='固定来源素材版本ID')


class HfUploadBinding(ContentRecord):
    __tablename__ = 'hf_upload_binding'
    __table_args__ = (
        UniqueConstraint('session_id', name='uq_hf_upload_binding_session'),
        CheckConstraint(
            'num_nonnulls(asset_version_id,price_source_id,reconciliation_batch_id,import_job_id)=1',
            name='ck_hf_upload_binding_target',
        ),
        *[
            Index('uq_hf_upload_binding_' + name, name, unique=True, postgresql_where=text(name + ' IS NOT NULL'))
            for name in ('asset_version_id', 'price_source_id', 'reconciliation_batch_id', 'import_job_id')
        ],
        {'comment': '上传完成结果唯一业务绑定', 'info': {'migration_managed': True}},
    )
    binding_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='绑定ID')
    session_id = Column(BigInteger, nullable=False, comment='上传会话ID')
    asset_version_id = Column(BigInteger, comment='素材版本ID')
    price_source_id = Column(BigInteger, comment='价格证据ID')
    reconciliation_batch_id = Column(BigInteger, comment='对账批次ID')
    import_job_id = Column(BigInteger, comment='导入任务ID')
    bound_by = Column(BigInteger, nullable=False, comment='执行绑定的上传所有者ID')


class HfFolderEntry(ContentRecord):
    __tablename__ = 'hf_folder_entry'
    __table_args__ = (
        CheckConstraint('num_nonnulls(asset_id,output_id,project_asset_ref_id)=1', name='ck_hf_folder_entry_target'),
        CheckConstraint('revision > 0', name='ck_hf_folder_entry_revision'),
        *[
            Index(
                'uq_hf_folder_entry_' + name,
                'space_id',
                name,
                unique=True,
                postgresql_where=text(name + ' IS NOT NULL'),
            )
            for name in ('asset_id', 'output_id', 'project_asset_ref_id')
        ],
        Index('ix_hf_folder_entry_folder', 'space_id', 'folder_id'),
        {'comment': '素材主目录归属', 'info': {'migration_managed': True}},
    )
    entry_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='目录归属ID')
    space_id = Column(BigInteger, nullable=False, comment='展示空间ID')
    folder_id = Column(BigInteger, comment='当前目录ID，空表示根层')
    asset_id = Column(BigInteger, comment='本空间素材ID')
    output_id = Column(BigInteger, comment='项目生成作品ID')
    project_asset_ref_id = Column(BigInteger, comment='跨项目引用ID')
    order_num = Column(Integer, nullable=False, server_default='0', comment='目录内顺序')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='归属并发修订')

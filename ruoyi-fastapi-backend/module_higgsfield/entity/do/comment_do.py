"""版本固定的评论、回复与随评论整体替换的图片标注。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfCommentThread(ContentRecord):
    __tablename__ = 'hf_comment_thread'
    __table_args__ = (
        CheckConstraint('num_nonnulls(asset_version_id,output_id)=1 AND create_user_id>0 AND (asset_version_id IS NULL OR asset_version_id>0) AND (output_id IS NULL OR output_id>0)', name='ck_hf_comment_thread_target'),
        Index('ix_hf_comment_thread_asset', 'asset_version_id', 'create_time'),
        Index('ix_hf_comment_thread_output', 'output_id', 'create_time'),
        {'comment': '评论主题及固定版本目标', 'info': {'migration_managed': True}},
    )
    thread_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='评论主题ID')
    asset_version_id = Column(BigInteger, comment='固定素材版本ID')
    output_id = Column(BigInteger, comment='固定作品ID')
    create_user_id = Column(BigInteger, nullable=False, comment='主题发起人ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='讨论并发修订')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='0存在2删除')
    resolved_time = Column(TIMESTAMP(timezone=True, precision=3), comment='协作处理时间')


class HfComment(ContentRecord):
    __tablename__ = 'hf_comment'
    __table_args__ = (
        UniqueConstraint('comment_id', 'thread_id', name='uq_hf_comment_thread_identity'),
        CheckConstraint("thread_id>0 AND author_id>0 AND revision>0 AND del_flag IN ('0','2') AND (parent_id IS NULL OR (parent_id>0 AND parent_id<>comment_id)) AND (video_time IS NULL OR video_time>=0) AND char_length(btrim(body))>0 AND char_length(body)<=5000", name='ck_hf_comment_fields'),
        Index('ix_hf_comment_thread_time', 'thread_id', 'create_time', 'comment_id'),
        {'comment': '评论正文及同主题回复', 'info': {'migration_managed': True}},
    )
    comment_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='评论ID')
    thread_id = Column(BigInteger, nullable=False, comment='固定主题ID')
    parent_id = Column(BigInteger, comment='同主题父评论ID')
    author_id = Column(BigInteger, nullable=False, comment='评论作者ID')
    body = Column(Text, nullable=False, comment='纯文本评论正文')
    video_time = Column(Numeric(18, 6), comment='视频定位秒数')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='评论并发修订')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='0存在2删除')


class HfAnnotation(ContentRecord):
    __tablename__ = 'hf_annotation'
    __table_args__ = (
        CheckConstraint("comment_id>0 AND shape IN ('point','rect','path') AND jsonb_typeof(geometry)='object' AND color ~ '^#[0-9a-f]{6}$' AND source_width>0 AND source_width<=100000 AND source_height>0 AND source_height<=100000", name='ck_hf_annotation_fields'),
        Index('ix_hf_annotation_comment', 'comment_id'),
        {'comment': '随评论修订整体替换的图片定位标注', 'info': {'migration_managed': True}},
    )
    annotation_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='图片标注ID')
    comment_id = Column(BigInteger, nullable=False, comment='所属评论ID')
    shape = Column(String(32), nullable=False, comment='形状：point点rect矩形path路径')
    geometry = Column(JSONB, nullable=False, comment='归一化坐标形状数据')
    color = Column(String(16), nullable=False, comment='小写六位十六进制颜色')
    source_width = Column(Integer, nullable=False, comment='标注原图像素宽度')
    source_height = Column(Integer, nullable=False, comment='标注原图像素高度')


class HfCommentReaction(ContentRecord):
    __tablename__ = 'hf_comment_reaction'
    __table_args__ = (UniqueConstraint('comment_id', 'user_id', 'emoji', name='uq_hf_comment_reaction_actor'),
        {'comment': '评论表情回应', 'info': {'migration_managed': True}})
    reaction_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='回应ID')
    comment_id = Column(BigInteger, nullable=False, comment='评论ID')
    user_id = Column(BigInteger, nullable=False, comment='回应用户ID')
    emoji = Column(String(32), nullable=False, comment='表情字符')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='0存在2取消')

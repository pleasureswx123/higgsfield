"""生成输出与独立归档状态，临时下载地址只允许加密保存。"""

from sqlalchemy import (
    BigInteger,
    Column,
    String,
    Integer,
    CHAR,
    Text,
    LargeBinary,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfGeneratedOutput(ContentRecord):
    __tablename__ = 'hf_generated_output'
    __table_args__ = (
        UniqueConstraint('job_id', 'ordinal', name='uq_hf_output_job_ordinal'),
        CheckConstraint(
            "ordinal>=0 AND revision>0 AND kind IN ('image','video','text') AND archive_state IN ('0','1','2','3','4','5') AND work_status IN ('0','1','2','3','4') AND del_flag IN ('0','2')",
            name='ck_hf_output_states',
        ),
        CheckConstraint(
            "(kind='text' AND text_content IS NOT NULL AND length(text_content)>0 AND archive_state='5' AND file_id IS NULL AND source_url_ciphertext IS NULL) OR (kind IN ('image','video') AND text_content IS NULL AND archive_state<>'5')",
            name='ck_hf_output_content',
        ),
        CheckConstraint("(archive_state='2')=(file_id IS NOT NULL)", name='ck_hf_output_archived_file'),
        CheckConstraint("jsonb_typeof(actual_metadata)='object'", name='ck_hf_output_metadata'),
        Index(
            'ix_hf_output_archive_retry',
            'archive_state',
            'next_retry_time',
            postgresql_where=text("archive_state IN ('3','0') AND del_flag='0'"),
        ),
        {'comment': '生成输出及独立归档状态', 'info': {'migration_managed': True}},
    )
    output_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='生成输出ID')
    job_id = Column(BigInteger, nullable=False, comment='所属生成任务ID')
    ordinal = Column(Integer, nullable=False, comment='供应商输出序号，从零开始')
    kind = Column(String(32), nullable=False, comment='输出类型：图片、视频或文本')
    file_id = Column(BigInteger, comment='成功归档的固定文件ID')
    text_content = Column(Text, comment='文本输出正文，非文本为空')
    archive_state = Column(
        CHAR(1), nullable=False, server_default='0', comment='归档：0未开始1归档中2已归档3失败4源过期5不适用'
    )
    source_url_ciphertext = Column(LargeBinary, comment='临时地址加密封装，包含密钥版本、随机数和认证标签')
    source_expires_time = Column(TIMESTAMP(timezone=True, precision=3), comment='临时源地址到期时间')
    actual_metadata = Column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment='受控实际尺寸时长格式及优化提示词，不含秘密地址',
    )
    next_retry_time = Column(TIMESTAMP(timezone=True, precision=3), comment='下次归档调度时间')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='输出并发版本')
    work_status = Column(
        CHAR(1), nullable=False, server_default='0', comment='工作状态：0无1制作中2待审核3已通过4已拒绝'
    )
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志：0存在2删除')

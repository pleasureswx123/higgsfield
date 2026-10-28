"""上游计费对象身份与不可变用量修订，不提供删除入口。"""

from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    CHAR,
    Numeric,
    CheckConstraint,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfBillingSubject(ContentRecord):
    __tablename__ = 'hf_billing_subject'
    __table_args__ = (
        CheckConstraint('(job_id IS NULL) <> (cost_center_id IS NULL)', name='ck_hf_billing_subject_owner'),
        CheckConstraint(
            "subject_kind IN ('generation','test','registration','query_fee') AND length(identity_key)>0",
            name='ck_hf_billing_subject_kind',
        ),
        UniqueConstraint('account_id', 'subject_kind', 'identity_key', name='uq_hf_billing_subject_local'),
        UniqueConstraint('origin_call_id', 'subject_kind', name='uq_hf_billing_subject_origin'),
        Index(
            'uq_hf_billing_subject_provider',
            'account_id',
            'subject_kind',
            'provider_object_id',
            unique=True,
            postgresql_where=text('provider_object_id IS NOT NULL'),
        ),
        {'comment': '上游计费对象身份', 'info': {'migration_managed': True}},
    )
    subject_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='计费对象ID')
    account_id = Column(BigInteger, nullable=False, comment='供应商账号ID')
    job_id = Column(BigInteger, comment='项目生成任务ID')
    cost_center_id = Column(BigInteger, comment='非项目消费归属ID')
    origin_call_id = Column(BigInteger, nullable=False, comment='原始调用ID')
    subject_kind = Column(String(32), nullable=False, comment='计费对象类型')
    provider_object_id = Column(String(255), comment='供应商计费对象ID')
    identity_key = Column(String(255), nullable=False, comment='稳定本地对象键')


class HfUsageRecord(ContentRecord):
    __tablename__ = 'hf_usage_record'
    __table_args__ = (
        UniqueConstraint('subject_id', 'revision_no', name='uq_hf_usage_revision'),
        UniqueConstraint('subject_id', 'payload_hash', name='uq_hf_usage_payload'),
        CheckConstraint(
            "revision_no>0 AND completeness IN ('available','partial','unknown') AND is_cumulative IN ('Y','N')",
            name='ck_hf_usage_state',
        ),
        CheckConstraint(
            'input_tokens>=0 AND output_tokens>=0 AND video_tokens>=0 AND image_count>=0 AND output_seconds>=0 AND reference_seconds>=0',
            name='ck_hf_usage_quantities',
        ),
        CheckConstraint(
            "payload_hash ~ '^[a-f0-9]{64}$' AND jsonb_typeof(raw_usage)='object' AND length(source_path)>0 AND length(parser_version)>0",
            name='ck_hf_usage_evidence',
        ),
        {'comment': '原始及归一用量修订，不同修订不可求和', 'info': {'migration_managed': True}},
    )
    usage_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='用量修订ID')
    subject_id = Column(BigInteger, nullable=False, comment='计费对象ID')
    call_id = Column(BigInteger, nullable=False, comment='用量来源调用ID')
    revision_no = Column(Integer, nullable=False, comment='对象内用量修订序号')
    input_tokens = Column(BigInteger, comment='实际输入Token数，未知为空')
    output_tokens = Column(BigInteger, comment='实际输出Token数，未知为空')
    video_tokens = Column(BigInteger, comment='实际视频Token数，未知为空')
    image_count = Column(Integer, comment='实际图片数量，未知为空')
    output_seconds = Column(Numeric(18, 6), comment='实际输出时长秒，未知为空')
    reference_seconds = Column(Numeric(18, 6), comment='实际参考时长秒，未知为空')
    completeness = Column(String(32), nullable=False, comment='用量完整性：available完整partial部分unknown未知')
    source_path = Column(String(200), nullable=False, comment='供应商用量字段路径')
    parser_version = Column(String(100), nullable=False, comment='用量归一规则版本')
    is_cumulative = Column(CHAR(1), nullable=False, comment='是否累计：Y是N否')
    payload_hash = Column(CHAR(64), nullable=False, comment='规范化用量证据SHA256摘要')
    raw_usage = Column(JSONB, nullable=False, comment='白名单脱敏原始用量证据')

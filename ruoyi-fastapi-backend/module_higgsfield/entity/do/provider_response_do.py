"""不可变供应商响应证据索引，原始内容保存在受控加密文件。"""

from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, String, UniqueConstraint

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderResponse(ContentRecord):
    __tablename__ = 'hf_provider_response'
    __table_args__ = (
        UniqueConstraint('provider_call_id', name='uq_hf_provider_response_call'),
        UniqueConstraint('storage_key', name='uq_hf_provider_response_key'),
        CheckConstraint(
            'byte_size > 0 AND http_status BETWEEN 100 AND 599 AND format_version=1',
            name='ck_hf_provider_response_values',
        ),
        CheckConstraint(
            "storage_key ~ '^provider-evidence/[a-f0-9]{32}$' AND sha256 ~ '^[a-f0-9]{64}$'",
            name='ck_hf_provider_response_file',
        ),
        {'comment': '不可变供应商响应证据索引', 'info': {'migration_managed': True}},
    )
    response_evidence_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='响应证据ID')
    provider_call_id = Column(BigInteger, nullable=False, comment='原始供应商调用ID')
    job_id = Column(BigInteger, nullable=False, comment='原始生成任务ID')
    storage_key = Column(String(100), nullable=False, comment='受控加密证据文件定位键')
    sha256 = Column(String(64), nullable=False, comment='加密文件SHA256摘要')
    byte_size = Column(BigInteger, nullable=False, comment='加密文件字节数')
    http_status = Column(Integer, nullable=False, comment='供应商HTTP响应状态码')
    format_version = Column(Integer, nullable=False, server_default='1', comment='证据封装版本')

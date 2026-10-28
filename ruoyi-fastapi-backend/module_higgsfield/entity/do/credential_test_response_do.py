"""非项目测试的不可变原始响应索引。"""
from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, String, UniqueConstraint
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfCredentialTestResponse(ContentRecord):
    __tablename__ = 'hf_credential_test_response'
    __table_args__ = (
        UniqueConstraint('test_id', name='uq_hf_test_response_test'),
        UniqueConstraint('provider_call_id', name='uq_hf_test_response_call'),
        UniqueConstraint('storage_key', name='uq_hf_test_response_key'),
        CheckConstraint('test_id>0 AND provider_call_id>0 AND byte_size>0 AND http_status BETWEEN 100 AND 599 AND format_version=1', name='ck_hf_test_response_values'),
        CheckConstraint("storage_key ~ '^provider-evidence/[a-f0-9]{32}$' AND sha256 ~ '^[a-f0-9]{64}$'", name='ck_hf_test_response_file'),
        {'comment': '凭据测试不可变响应证据索引', 'info': {'migration_managed': True}},
    )
    response_evidence_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='测试响应证据ID')
    test_id = Column(BigInteger, nullable=False, comment='原始凭据测试ID')
    provider_call_id = Column(BigInteger, nullable=False, comment='原始测试供应商调用ID')
    storage_key = Column(String(100), nullable=False, comment='受控加密证据文件定位键')
    sha256 = Column(String(64), nullable=False, comment='加密文件SHA256摘要')
    byte_size = Column(BigInteger, nullable=False, comment='加密文件字节数')
    http_status = Column(Integer, nullable=False, comment='供应商HTTP响应状态码')
    format_version = Column(Integer, nullable=False, server_default='1', comment='证据封装版本')

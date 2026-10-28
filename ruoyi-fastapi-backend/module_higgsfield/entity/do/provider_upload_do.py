"""外部临时上传运行事实，过期后允许新上传但不删除旧证据。"""

from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, Index, LargeBinary, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderUpload(ContentRecord):
    __tablename__ = 'hf_provider_upload'
    __table_args__ = (
        UniqueConstraint('provider_call_id', name='uq_hf_provider_upload_call'),
        CheckConstraint("state IN ('0','1','2','3','4')", name='ck_hf_provider_upload_state'),
        CheckConstraint(
            "(state IN ('1','4') AND url_ciphertext IS NOT NULL AND expires_time IS NOT NULL AND expires_time>create_time) "
            "OR (state IN ('0','2','3') AND url_ciphertext IS NULL AND expires_time IS NULL)",
            name='ck_hf_provider_upload_source',
        ),
        Index(
            'ix_hf_provider_upload_reuse',
            'asset_version_id',
            'account_id',
            'credential_version_id',
            text('expires_time DESC'),
        ),
        {'comment': '外部临时上传及加密地址，不替代平台长期文件', 'info': {'migration_managed': True}},
    )
    provider_upload_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='外部临时上传ID')
    asset_version_id = Column(BigInteger, nullable=False, comment='固定源素材版本ID')
    account_id = Column(BigInteger, nullable=False, comment='供应商账号范围ID')
    credential_version_id = Column(BigInteger, nullable=False, comment='本次上传原始凭据版本ID')
    provider_call_id = Column(BigInteger, nullable=False, comment='本次上传调用事实ID')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0上传中1可用2失败3未知4过期')
    url_ciphertext = Column(LargeBinary, comment='绑定上传身份和原凭据的加密临时URL')
    expires_time = Column(TIMESTAMP(timezone=True, precision=3), comment='已扣除安全余量的到期时间')

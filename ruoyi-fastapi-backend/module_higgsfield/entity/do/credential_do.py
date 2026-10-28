"""凭据身份与加密版本；禁止通用读取接口暴露密文字段。"""

from sqlalchemy import BigInteger, Column, String, Integer, CHAR, LargeBinary, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderCredential(ContentRecord):
    __tablename__ = 'hf_provider_credential'
    __table_args__ = (
        UniqueConstraint('account_id', 'credential_name', name='uq_hf_credential_name'),
        UniqueConstraint('credential_id', 'account_id', name='uq_hf_credential_account'),
        CheckConstraint("status IN ('0','1','2','3','4') AND revision>0", name='ck_hf_credential_state'),
        {'comment': '供应商凭据身份，不含密钥明文', 'info': {'migration_managed': True}},
    )
    credential_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='凭据身份ID')
    account_id = Column(BigInteger, nullable=False, comment='所属供应商账号ID')
    credential_name = Column(String(200), nullable=False, comment='凭据管理名称')
    owner_id = Column(BigInteger, nullable=False, comment='责任人用户ID')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1启用2排空3停用4撤销')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='元数据并发版本')


class HfCredentialVersion(ContentRecord):
    __tablename__ = 'hf_credential_version'
    __table_args__ = (
        UniqueConstraint('credential_id', 'version_no', name='uq_hf_credential_version_no'),
        UniqueConstraint('master_key_version', 'nonce', name='uq_hf_credential_nonce'),
        CheckConstraint(
            "state IN ('0','1','2','3','4') AND revision>0 AND version_no>0", name='ck_hf_credential_version_state'
        ),
        CheckConstraint(
            'octet_length(nonce)=12 AND octet_length(auth_tag)=16 AND octet_length(secret_ciphertext)>0',
            name='ck_hf_credential_encryption',
        ),
        CheckConstraint('valid_until IS NULL OR valid_until>valid_from', name='ck_hf_credential_validity'),
        Index('ix_hf_credential_version_state', 'credential_id', 'state'),
        {'comment': '绑定配置的加密供应商密钥版本', 'info': {'migration_managed': True}},
    )
    credential_version_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='加密凭据版本ID')
    credential_id = Column(BigInteger, nullable=False, comment='凭据身份ID')
    connection_version_id = Column(BigInteger, nullable=False, comment='固定供应商连接配置版本ID')
    version_no = Column(Integer, nullable=False, comment='凭据内部版本号')
    secret_ciphertext = Column(LargeBinary, nullable=False, comment='认证加密后的密文，不向管理员返回')
    nonce = Column(LargeBinary, nullable=False, comment='十二字节随机数，同主密钥版本唯一')
    auth_tag = Column(LargeBinary, nullable=False, comment='十六字节认证标签')
    master_key_version = Column(String(100), nullable=False, comment='运行时主密钥版本，主密钥不入库')
    fingerprint = Column(String(128), nullable=False, comment='带密钥摘要指纹，仅用于内部匹配')
    masked_suffix = Column(String(8), nullable=False, comment='掩码及末尾四字符')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1启用2排空3停用4撤销')
    valid_from = Column(TIMESTAMP(timezone=True), nullable=False, comment='有效期起点')
    valid_until = Column(TIMESTAMP(timezone=True), comment='有效期终点')
    revoked_time = Column(TIMESTAMP(timezone=True), comment='撤销时间')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='状态并发版本')

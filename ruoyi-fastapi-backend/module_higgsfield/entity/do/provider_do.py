"""连接配置版本独立保留，任务和凭据不能随当前地址漂移。"""

from sqlalchemy import BigInteger, Column, Integer, String, Text, CHAR, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderConnectionVersion(ContentRecord):
    __tablename__ = 'hf_provider_connection_version'
    __table_args__ = (
        UniqueConstraint('connection_id', 'version_no', name='uq_hf_connection_version_no'),
        UniqueConstraint('connection_id', 'connection_version_id', name='uq_hf_connection_version_identity'),
        CheckConstraint('version_no>0', name='ck_hf_connection_version_no'),
        {'comment': '不可变供应商连接配置版本', 'info': {'migration_managed': True}},
    )
    connection_version_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='连接配置版本ID')
    connection_id = Column(BigInteger, nullable=False, comment='所属连接身份ID')
    version_no = Column(Integer, nullable=False, comment='内部配置版本号')
    base_url = Column(Text, nullable=False, comment='登记的供应商地址，不代表已通过传输验证')
    adapter_version = Column(String(100), nullable=False, comment='固定适配器版本')
    config = Column(JSONB, nullable=False, comment='白名单非秘密配置')
    config_hash = Column(CHAR(64), nullable=False, comment='地址适配器及配置规范化摘要')


class HfProviderAccount(ContentRecord):
    __tablename__ = 'hf_provider_account'
    __table_args__ = (
        UniqueConstraint(
            'connection_id', 'account_code', 'region', 'upstream_project', name='uq_hf_provider_account_scope'
        ),
        UniqueConstraint('account_id', 'connection_id', name='uq_hf_provider_account_connection'),
        CheckConstraint("status IN ('0','1')", name='ck_hf_provider_account_status'),
        {'comment': '供应商账号及素材作用域', 'info': {'migration_managed': True}},
    )
    account_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='供应商账号ID')
    connection_id = Column(BigInteger, nullable=False, comment='所属供应商连接ID')
    account_code = Column(String(100), nullable=False, comment='公司登记的供应商账号编码')
    region = Column(String(32), nullable=False, comment='明确的供应商区域作用域')
    upstream_project = Column(String(100), nullable=False, comment='供应商侧项目标识，不以业务项目名代替')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0正常1停用')

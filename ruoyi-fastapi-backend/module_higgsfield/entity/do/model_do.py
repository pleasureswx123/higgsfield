"""模型身份、不可变能力版本与精确规格；不保存供应商秘密。"""

from sqlalchemy import BigInteger, Column, String, Integer, Text, CHAR, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderConnection(ContentRecord):
    __tablename__ = 'hf_provider_connection'
    __table_args__ = (
        UniqueConstraint('environment', 'connection_name', name='uq_hf_connection_name'),
        CheckConstraint(
            "environment IN ('test','production') AND status IN ('0','1','2') AND revision>0",
            name='ck_hf_connection_state',
        ),
        {'comment': '供应商连接身份', 'info': {'migration_managed': True}},
    )
    connection_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='连接ID')
    connection_name = Column(String(200), nullable=False, comment='连接名称')
    environment = Column(String(32), nullable=False, comment='测试或正式环境')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1启用2停用')
    current_version_id = Column(BigInteger, comment='当前连接配置版本ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')


class HfModelProfile(ContentRecord):
    __tablename__ = 'hf_model_profile'
    __table_args__ = (
        UniqueConstraint('connection_id', 'code', name='uq_hf_model_code'),
        CheckConstraint("kind IN ('chat','image','video')", name='ck_hf_model_kind'),
        {'comment': '模型能力身份', 'info': {'migration_managed': True}},
    )
    model_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='模型ID')
    connection_id = Column(BigInteger, nullable=False, comment='供应商连接ID')
    code = Column(String(100), nullable=False, comment='平台稳定模型码')
    display_name = Column(String(200), nullable=False, comment='模型展示名称')
    kind = Column(String(32), nullable=False, comment='模型任务类型')


class HfModelProfileVersion(ContentRecord):
    __tablename__ = 'hf_model_profile_version'
    __table_args__ = (
        UniqueConstraint('model_id', 'version_no', name='uq_hf_model_version_no'),
        UniqueConstraint('model_id', 'model_version_id', name='uq_hf_model_version_identity'),
        CheckConstraint(
            "version_no>0 AND schema_version=1 AND revision>0 AND status IN ('0','1','2','3')",
            name='ck_hf_model_version_state',
        ),
        {'comment': '模型不可变能力版本', 'info': {'migration_managed': True}},
    )
    model_version_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='能力版本ID')
    model_id = Column(BigInteger, nullable=False, comment='模型身份ID')
    version_no = Column(Integer, nullable=False, comment='模型内部版本号')
    gateway_alias = Column(String(100), nullable=False, comment='精确上游调用别名')
    underlying_model_id = Column(String(255), comment='已确认底层版本标识，未知为空')
    region = Column(String(32), nullable=False, comment='账号及素材区域作用域')
    capabilities = Column(JSONB, nullable=False, comment='白名单模型能力配置')
    schema_version = Column(Integer, nullable=False, server_default='1', comment='能力结构契约版本')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0草稿1已验证2已发布3停用')
    verification_ref = Column(Text, comment='已审阅的脱敏联调证据位置')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='并发版本')


class HfModelVariant(ContentRecord):
    __tablename__ = 'hf_model_variant'
    __table_args__ = (
        UniqueConstraint('model_version_id', 'variant_key', name='uq_hf_model_variant_key'),
        UniqueConstraint('variant_id', 'model_version_id', name='uq_hf_model_variant_identity'),
        {'comment': '模型精确计价规格', 'info': {'migration_managed': True}},
    )
    variant_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='规格ID')
    model_version_id = Column(BigInteger, nullable=False, comment='所属能力版本ID')
    variant_key = Column(String(200), nullable=False, comment='规范化完整条件摘要键')
    dimensions = Column(JSONB, nullable=False, comment='完整计价条件，不允许通配符')

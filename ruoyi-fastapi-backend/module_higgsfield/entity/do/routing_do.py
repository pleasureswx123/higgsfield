"""项目整组路由与候选凭据；子行修改必须持有整组锁。"""

from sqlalchemy import BigInteger, Column, Integer, CHAR, UniqueConstraint, CheckConstraint, Index
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProjectRoutingSet(ContentRecord):
    __tablename__ = 'hf_project_routing_set'
    __table_args__ = (
        UniqueConstraint('project_id', name='uq_hf_routing_set_project'),
        CheckConstraint('revision>0', name='ck_hf_routing_set_revision'),
        {'comment': '项目整组模型路由并发版本', 'info': {'migration_managed': True}},
    )
    routing_set_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='路由组ID')
    project_id = Column(BigInteger, nullable=False, comment='所属项目ID，一个项目一组')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='整组并发版本')


class HfProjectProviderConfig(ContentRecord):
    __tablename__ = 'hf_project_provider_config'
    __table_args__ = (
        UniqueConstraint('project_id', 'model_id', 'account_id', name='uq_hf_project_model_account'),
        CheckConstraint("status IN ('0','1') AND priority>=0 AND revision>0", name='ck_hf_project_route'),
        Index('ix_hf_project_route_priority', 'project_id', 'model_id', 'status', 'priority'),
        {'comment': '项目模型到供应商账号的显式路由', 'info': {'migration_managed': True}},
    )
    config_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='项目路由配置ID')
    project_id = Column(BigInteger, nullable=False, comment='所属项目及路由组ID')
    model_id = Column(BigInteger, nullable=False, comment='模型身份ID')
    account_id = Column(BigInteger, nullable=False, comment='供应商账号ID')
    status = Column(CHAR(1), nullable=False, server_default='1', comment='状态：0启用1停用')
    priority = Column(Integer, nullable=False, server_default='100', comment='路由优先级，数值越小越优先')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='路由内部修订号')


class HfRoutingPolicy(ContentRecord):
    __tablename__ = 'hf_routing_policy'
    __table_args__ = (
        UniqueConstraint('project_provider_config_id', 'credential_id', name='uq_hf_route_credential'),
        CheckConstraint("priority>=0 AND max_concurrency>0 AND enabled IN ('Y','N')", name='ck_hf_routing_policy'),
        {'comment': '项目显式路由候选凭据及并发上限', 'info': {'migration_managed': True}},
    )
    policy_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='路由凭据候选ID')
    project_provider_config_id = Column(BigInteger, nullable=False, comment='项目路由配置ID')
    credential_id = Column(BigInteger, nullable=False, comment='候选凭据身份ID')
    priority = Column(Integer, nullable=False, server_default='100', comment='凭据优先级，数值越小越优先')
    max_concurrency = Column(Integer, nullable=False, comment='候选凭据最大并发数')
    enabled = Column(CHAR(1), nullable=False, server_default='N', comment='是否启用：Y是N否')

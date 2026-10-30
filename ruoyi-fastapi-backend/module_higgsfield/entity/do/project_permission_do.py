"""每个项目独立保存角色权限覆盖，不修改全局角色模板。"""
from sqlalchemy import BigInteger, Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from common.mixin import AuditTimeMixin
from config.database import Base


class HfProjectPermissionConfig(AuditTimeMixin, Base):
    __tablename__ = 'hf_project_permission_config'
    __table_args__ = (UniqueConstraint('project_id', name='uq_hf_project_permission_config_project'), {'comment': '项目角色权限配置', 'info': {'migration_managed': True}})
    config_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='配置ID')
    project_id = Column(BigInteger, nullable=False, comment='项目ID')
    revision = Column(BigInteger, nullable=False, comment='并发版本')
    overrides = Column(JSONB, nullable=False, comment='按角色代码保存权限覆盖及范围，none表示禁用')
    create_by = Column(String(64), nullable=False, comment='创建者')
    update_by = Column(String(64), nullable=False, comment='更新者')

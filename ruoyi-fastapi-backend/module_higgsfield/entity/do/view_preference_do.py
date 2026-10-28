"""仅属于本人的页面偏好，不参与权限判定。"""
from sqlalchemy import BigInteger, CheckConstraint, Column, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from config.database import Base
from module_higgsfield.entity.do.project_preference_do import PreferenceAudit


class HfUserViewPreference(PreferenceAudit, Base):
    __tablename__ = 'hf_user_view_preference'
    __table_args__ = (
        CheckConstraint('user_id>0 AND revision>0 AND (project_id IS NULL OR project_id>0)', name='ck_hf_view_preference_identity'),
        CheckConstraint("view_key IN ('projects','library','elements') AND jsonb_typeof(settings)='object'", name='ck_hf_view_preference_settings'),
        Index('uq_hf_view_preference_global', 'user_id', 'view_key', unique=True, postgresql_where=text('project_id IS NULL')),
        Index('uq_hf_view_preference_project', 'user_id', 'view_key', 'project_id', unique=True, postgresql_where=text('project_id IS NOT NULL')),
        {'comment': '本人页面布局与筛选偏好', 'info': {'migration_managed': True}},
    )
    preference_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='偏好ID')
    user_id = Column(BigInteger, nullable=False, comment='所属用户ID')
    view_key = Column(String(100), nullable=False, comment='页面稳定标识')
    project_id = Column(BigInteger, nullable=True, comment='项目ID，空值表示全局视图')
    settings = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='白名单布局与筛选设置')
    revision = Column(BigInteger, nullable=False, server_default=text('1'), comment='并发修订')

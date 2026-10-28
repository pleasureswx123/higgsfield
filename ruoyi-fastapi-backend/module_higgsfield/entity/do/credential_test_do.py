"""凭据测试固定配置与消费归属，完成事实不可伪装成排队成功。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfCredentialTest(ContentRecord):
    __tablename__ = 'hf_credential_test'
    __table_args__ = (
        CheckConstraint("config_hash ~ '^[0-9a-f]{64}$'", name='ck_hf_credential_test_hash'),
        CheckConstraint("jsonb_typeof(result)='object'", name='ck_hf_credential_test_result'),
        CheckConstraint("state IN ('0','1','2') AND ((state='0' AND finished_time IS NULL) OR (state IN ('1','2') AND finished_time IS NOT NULL))", name='ck_hf_credential_test_state'),
        CheckConstraint("state<>'1' OR provider_call_id IS NOT NULL", name='ck_hf_credential_test_passed_call'),
        CheckConstraint('credential_version_id>0 AND connection_version_id>0 AND cost_center_id>0 AND requested_by>0', name='ck_hf_credential_test_identity'),
        Index('ix_hf_credential_test_version', 'credential_version_id', 'create_time'),
        Index('ix_hf_credential_test_pending', 'state', 'create_time'),
        {'comment': '绑定精确配置的凭据测试及非项目消费证据', 'info': {'migration_managed': True}},
    )
    test_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='凭据测试ID')
    credential_version_id = Column(BigInteger, nullable=False, comment='被测凭据版本ID')
    connection_version_id = Column(BigInteger, nullable=False, comment='固定连接配置版本ID')
    config_hash = Column(CHAR(64), nullable=False, comment='完整测试配置摘要')
    model_version_id = Column(BigInteger, comment='被测模型能力版本ID，非模型测试为空')
    cost_center_id = Column(BigInteger, nullable=False, comment='管理消费归属成本中心ID')
    requested_by = Column(BigInteger, nullable=False, comment='发起测试的用户ID')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='测试状态：0待执行1通过2失败')
    provider_call_id = Column(BigInteger, comment='真实测试调用ID，未发送为空')
    finished_time = Column(TIMESTAMP(timezone=True, precision=3), comment='测试完成时间')
    result = Column(JSONB, nullable=False, comment='脱敏诊断事实，不含秘密或原始响应')

"""外部请求运行事实；调用次数与计费对象数量分别记录。"""

from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfProviderCall(ContentRecord):
    __tablename__ = 'hf_provider_call'
    __table_args__ = (
        CheckConstraint('(job_id IS NOT NULL)<>(cost_center_id IS NOT NULL)', name='ck_hf_call_subject'),
        CheckConstraint(
            "state IN ('0','1','2','3') AND acceptance IN ('accepted','rejected','unknown','not_applicable')",
            name='ck_hf_call_state',
        ),
        CheckConstraint(
            "operation IN ('chat','image','video_submit','video_poll','upload','register','asset_get','test')",
            name='ck_hf_call_operation',
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(request_metadata)='object' AND (response_metadata IS NULL OR jsonb_typeof(response_metadata)='object')",
            name='ck_hf_call_metadata',
        ),
        CheckConstraint('http_status IS NULL OR http_status BETWEEN 100 AND 599', name='ck_hf_call_http'),
        CheckConstraint(
            "(state='0' AND started_time IS NULL AND finished_time IS NULL) OR (state='1' AND started_time IS NOT NULL AND finished_time IS NULL) OR (state IN ('2','3') AND started_time IS NOT NULL AND finished_time IS NOT NULL AND finished_time>=started_time)",
            name='ck_hf_call_times',
        ),
        CheckConstraint("state NOT IN ('0','1','3') OR acceptance='unknown'", name='ck_hf_call_acceptance'),
        Index('ix_hf_call_job_created', 'job_id', 'create_time'),
        Index('ix_hf_call_account_created', 'account_id', 'create_time'),
        Index('ix_hf_call_state_started', 'state', 'started_time'),
        {'comment': '供应商真实请求意图及运行事实，不代表独立收费', 'info': {'migration_managed': True}},
    )
    call_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='外部调用ID')
    job_id = Column(BigInteger, comment='生成任务来源，与成本中心恰选其一')
    cost_center_id = Column(BigInteger, comment='非项目调用的成本中心ID')
    account_id = Column(BigInteger, nullable=False, comment='本次调用供应商账号ID')
    credential_version_id = Column(BigInteger, nullable=False, comment='本次实际凭据版本ID')
    operation = Column(String(32), nullable=False, comment='调用操作：对话图片视频提交轮询上传注册查询测试')
    request_hash = Column(CHAR(64), nullable=False, comment='规范请求摘要，不存授权头')
    request_metadata = Column(JSONB, nullable=False, comment='白名单脱敏请求及配置版本，不含秘密')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='状态：0计划1发送中2已完成3未知')
    acceptance = Column(
        String(32),
        nullable=False,
        server_default='unknown',
        comment='受理事实：accepted rejected unknown not_applicable',
    )
    http_status = Column(Integer, comment='响应HTTP状态码，未收到为空')
    business_code = Column(String(100), comment='白名单供应商业务码')
    response_metadata = Column(JSONB, comment='白名单脱敏响应，不含Base64或秘密URL')
    response_id = Column(String(255), comment='外层上游响应ID')
    actor_id = Column(BigInteger, comment='管理测试发起者，任务调用由任务追溯')
    started_time = Column(TIMESTAMP(timezone=True, precision=3), comment='开始发送时点')
    finished_time = Column(TIMESTAMP(timezone=True, precision=3), comment='响应记录或判定未知时点，不证明上游完成')

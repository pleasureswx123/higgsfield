"""任务输入快照、运行状态和固定素材引用。"""

from sqlalchemy import BigInteger, Column, String, Integer, CHAR, CheckConstraint, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfCreationJob(ContentRecord):
    __tablename__ = 'hf_creation_job'
    __table_args__ = (
        UniqueConstraint('actor_id', 'project_id', 'idempotency_key', name='uq_hf_job_request'),
        UniqueConstraint('job_id', 'project_id', name='uq_hf_job_project'),
        CheckConstraint(
            "kind IN ('chat','image','video') AND orchestration_state IN ('0','1','2','3','4','5','6') AND upstream_state IN ('0','1','2','3','4','5','6') AND billing_state IN ('0','1','2','3') AND cancel_state IN ('0','1','2','3','4') AND revision>0 AND fencing_token>=0 AND attempt_count>=0 AND event_sequence>=0",
            name='ck_hf_job_states',
        ),
        CheckConstraint(
            "(kind='chat' AND chat_session_id IS NOT NULL AND context_session_revision IS NOT NULL AND context_session_revision>0) OR (kind<>'chat' AND chat_session_id IS NULL AND context_session_revision IS NULL)",
            name='ck_hf_job_chat_context',
        ),
        CheckConstraint('(lease_owner IS NULL)=(lease_until IS NULL)', name='ck_hf_job_lease'),
        Index('ix_hf_job_project_created', 'project_id', text('create_time DESC'), text('job_id DESC')),
        Index('ix_hf_job_actor_created', 'actor_id', text('create_time DESC'), text('job_id DESC')),
        Index('ix_hf_job_schedule', 'next_action_time', 'job_id', postgresql_where=text("orchestration_state<>'5'")),
        Index('ix_hf_job_chat', 'chat_session_id', 'create_time', 'job_id'),
        Index(
            'ix_hf_job_credential_inflight',
            'credential_version_id',
            postgresql_where=text("orchestration_state<>'5' OR upstream_state IN ('1','2','6')"),
        ),
        {'comment': '生成任务固定快照及独立运行状态', 'info': {'migration_managed': True}},
    )
    job_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='生成任务ID')
    project_id = Column(BigInteger, nullable=False, comment='任务费用与内容项目ID')
    actor_id = Column(BigInteger, nullable=False, comment='任务发起用户ID')
    dept_id = Column(BigInteger, comment='任务发生时部门ID')
    department_snapshot = Column(JSONB, nullable=False, comment='部门名称与路径历史快照')
    kind = Column(String(32), nullable=False, comment='任务类型：对话、图片或视频')
    idempotency_key = Column(String(128), nullable=False, comment='原请求作用域与幂等键组合摘要')
    request_hash = Column(CHAR(64), nullable=False, comment='规范化任务提交摘要')
    model_version_id = Column(BigInteger, nullable=False, comment='固定模型能力版本ID')
    model_variant_id = Column(BigInteger, nullable=False, comment='固定精确计价规格ID')
    credential_version_id = Column(BigInteger, nullable=False, comment='原始提交凭据版本ID，不保存密钥正文')
    platform_price_version_id = Column(BigInteger, nullable=False, comment='固定平台价格版本ID')
    procurement_price_version_id = Column(BigInteger, comment='固定采购价格版本ID，未知为空')
    exchange_rate_version_id = Column(BigInteger, comment='固定汇率版本ID')
    input_snapshot = Column(JSONB, nullable=False, comment='提示词参数模型适配器及预估依据快照，不含秘密')
    orchestration_state = Column(
        CHAR(1), nullable=False, server_default='0', comment='编排：0已受理1准备2提交3提交未知4执行5结束6阻塞'
    )
    upstream_state = Column(
        CHAR(1), nullable=False, server_default='0', comment='上游：0未提交1排队2执行3成功4失败5取消6未知'
    )
    billing_state = Column(CHAR(1), nullable=False, server_default='0', comment='费用：0待定1已计算2已确认3争议')
    upstream_task_id = Column(String(255), comment='内层上游任务ID')
    upstream_response_id = Column(String(255), comment='外层上游响应ID')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='任务聚合并发版本')
    next_action_time = Column(TIMESTAMP(timezone=True, precision=3), comment='下次调度时间')
    lease_owner = Column(String(100), comment='当前执行实例')
    lease_until = Column(TIMESTAMP(timezone=True, precision=3), comment='执行租约截止')
    fencing_token = Column(BigInteger, nullable=False, server_default='0', comment='单调递增执行栅栏令牌')
    attempt_count = Column(Integer, nullable=False, server_default='0', comment='阶段执行次数')
    finished_time = Column(TIMESTAMP(timezone=True, precision=3), comment='编排结束时间，不代表费用或归档完成')
    cancel_state = Column(CHAR(1), nullable=False, server_default='0', comment='取消：0无1请求2确认3拒绝4不支持')
    event_sequence = Column(BigInteger, nullable=False, server_default='0', comment='最后已提交任务事件序号')
    chat_session_id = Column(BigInteger, comment='对话会话ID，非对话任务为空')
    context_session_revision = Column(BigInteger, comment='冻结对话上下文时的会话版本')


class HfJobReference(ContentRecord):
    __tablename__ = 'hf_job_reference'
    __table_args__ = (
        UniqueConstraint('job_id', 'ordinal', name='uq_hf_job_reference_order'),
        UniqueConstraint('job_id', 'asset_version_id', 'media_role', name='uq_hf_job_reference_role'),
        CheckConstraint('ordinal>=0', name='ck_hf_job_reference_order'),
        {'comment': '任务固定输入引用，不随素材更新漂移', 'info': {'migration_managed': True}},
    )
    reference_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='任务引用ID')
    job_id = Column(BigInteger, nullable=False, comment='所属生成任务ID')
    asset_version_id = Column(BigInteger, nullable=False, comment='精确素材版本ID')
    element_revision_id = Column(BigInteger, comment='元素修订来源ID')
    media_role = Column(String(32), nullable=False, comment='模型输入媒体角色')
    ordinal = Column(Integer, nullable=False, comment='编译顺序')
    reference_snapshot = Column(JSONB, nullable=False, comment='授权与展示快照，不含签名地址')

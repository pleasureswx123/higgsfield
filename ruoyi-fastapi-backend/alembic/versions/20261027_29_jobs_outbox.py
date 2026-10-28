"""任务固定快照、事件序列与事务发件箱。"""

from alembic import op

revision = '20261027_29'
down_revision = '20261027_28'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_creation_job (\n\tjob_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\tdept_id BIGINT, \n\tdepartment_snapshot JSONB NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tidempotency_key VARCHAR(128) NOT NULL, \n\trequest_hash CHAR(64) NOT NULL, \n\tmodel_version_id BIGINT NOT NULL, \n\tmodel_variant_id BIGINT NOT NULL, \n\tcredential_version_id BIGINT NOT NULL, \n\tplatform_price_version_id BIGINT NOT NULL, \n\tprocurement_price_version_id BIGINT, \n\texchange_rate_version_id BIGINT, \n\tinput_snapshot JSONB NOT NULL, \n\torchestration_state CHAR(1) DEFAULT '0' NOT NULL, \n\tupstream_state CHAR(1) DEFAULT '0' NOT NULL, \n\tbilling_state CHAR(1) DEFAULT '0' NOT NULL, \n\tupstream_task_id VARCHAR(255), \n\tupstream_response_id VARCHAR(255), \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tnext_action_time TIMESTAMP(3) WITH TIME ZONE, \n\tlease_owner VARCHAR(100), \n\tlease_until TIMESTAMP(3) WITH TIME ZONE, \n\tfencing_token BIGINT DEFAULT '0' NOT NULL, \n\tattempt_count INTEGER DEFAULT '0' NOT NULL, \n\tfinished_time TIMESTAMP(3) WITH TIME ZONE, \n\tcancel_state CHAR(1) DEFAULT '0' NOT NULL, \n\tevent_sequence BIGINT DEFAULT '0' NOT NULL, \n\tchat_session_id BIGINT, \n\tcontext_session_revision BIGINT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (job_id), \n\tCONSTRAINT uq_hf_job_request UNIQUE (actor_id, project_id, idempotency_key), \n\tCONSTRAINT uq_hf_job_project UNIQUE (job_id, project_id), \n\tCONSTRAINT ck_hf_job_states CHECK (kind IN ('chat','image','video') AND orchestration_state IN ('0','1','2','3','4','5','6') AND upstream_state IN ('0','1','2','3','4','5','6') AND billing_state IN ('0','1','2','3') AND cancel_state IN ('0','1','2','3','4') AND revision>0 AND fencing_token>=0 AND attempt_count>=0 AND event_sequence>=0), \n\tCONSTRAINT ck_hf_job_chat_context CHECK ((kind='chat' AND chat_session_id IS NOT NULL AND context_session_revision IS NOT NULL AND context_session_revision>0) OR (kind<>'chat' AND chat_session_id IS NULL AND context_session_revision IS NULL)), \n\tCONSTRAINT ck_hf_job_lease CHECK ((lease_owner IS NULL)=(lease_until IS NULL))\n)"
    )
    op.execute("COMMENT ON TABLE hf_creation_job IS '生成任务固定快照及独立运行状态'")
    op.execute("COMMENT ON COLUMN hf_creation_job.job_id IS '生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.project_id IS '任务费用与内容项目ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.actor_id IS '任务发起用户ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.dept_id IS '任务发生时部门ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.department_snapshot IS '部门名称与路径历史快照'")
    op.execute("COMMENT ON COLUMN hf_creation_job.kind IS '任务类型：对话、图片或视频'")
    op.execute("COMMENT ON COLUMN hf_creation_job.idempotency_key IS '原请求作用域与幂等键组合摘要'")
    op.execute("COMMENT ON COLUMN hf_creation_job.request_hash IS '规范化任务提交摘要'")
    op.execute("COMMENT ON COLUMN hf_creation_job.model_version_id IS '固定模型能力版本ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.model_variant_id IS '固定精确计价规格ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.credential_version_id IS '原始提交凭据版本ID，不保存密钥正文'")
    op.execute("COMMENT ON COLUMN hf_creation_job.platform_price_version_id IS '固定平台价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.procurement_price_version_id IS '固定采购价格版本ID，未知为空'")
    op.execute("COMMENT ON COLUMN hf_creation_job.exchange_rate_version_id IS '固定汇率版本ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.input_snapshot IS '提示词参数模型适配器及预估依据快照，不含秘密'")
    op.execute(
        "COMMENT ON COLUMN hf_creation_job.orchestration_state IS '编排：0已受理1准备2提交3提交未知4执行5结束6阻塞'"
    )
    op.execute("COMMENT ON COLUMN hf_creation_job.upstream_state IS '上游：0未提交1排队2执行3成功4失败5取消6未知'")
    op.execute("COMMENT ON COLUMN hf_creation_job.billing_state IS '费用：0待定1已计算2已确认3争议'")
    op.execute("COMMENT ON COLUMN hf_creation_job.upstream_task_id IS '内层上游任务ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.upstream_response_id IS '外层上游响应ID'")
    op.execute("COMMENT ON COLUMN hf_creation_job.revision IS '任务聚合并发版本'")
    op.execute("COMMENT ON COLUMN hf_creation_job.next_action_time IS '下次调度时间'")
    op.execute("COMMENT ON COLUMN hf_creation_job.lease_owner IS '当前执行实例'")
    op.execute("COMMENT ON COLUMN hf_creation_job.lease_until IS '执行租约截止'")
    op.execute("COMMENT ON COLUMN hf_creation_job.fencing_token IS '单调递增执行栅栏令牌'")
    op.execute("COMMENT ON COLUMN hf_creation_job.attempt_count IS '阶段执行次数'")
    op.execute("COMMENT ON COLUMN hf_creation_job.finished_time IS '编排结束时间，不代表费用或归档完成'")
    op.execute("COMMENT ON COLUMN hf_creation_job.cancel_state IS '取消：0无1请求2确认3拒绝4不支持'")
    op.execute("COMMENT ON COLUMN hf_creation_job.event_sequence IS '最后已提交任务事件序号'")
    op.execute("COMMENT ON COLUMN hf_creation_job.chat_session_id IS '对话会话ID，非对话任务为空'")
    op.execute("COMMENT ON COLUMN hf_creation_job.context_session_revision IS '冻结对话上下文时的会话版本'")
    op.execute("COMMENT ON COLUMN hf_creation_job.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_creation_job.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_creation_job.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_creation_job.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_job_actor_created ON hf_creation_job (actor_id, create_time DESC, job_id DESC)')
    op.execute('CREATE INDEX ix_hf_job_chat ON hf_creation_job (chat_session_id, create_time, job_id)')
    op.execute('CREATE INDEX ix_hf_job_project_created ON hf_creation_job (project_id, create_time DESC, job_id DESC)')
    op.execute(
        "CREATE INDEX ix_hf_job_schedule ON hf_creation_job (next_action_time, job_id) WHERE orchestration_state<>'5'"
    )
    op.execute(
        "CREATE TABLE hf_job_reference (\n\treference_id BIGSERIAL NOT NULL, \n\tjob_id BIGINT NOT NULL, \n\tasset_version_id BIGINT NOT NULL, \n\telement_revision_id BIGINT, \n\tmedia_role VARCHAR(32) NOT NULL, \n\tordinal INTEGER NOT NULL, \n\treference_snapshot JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (reference_id), \n\tCONSTRAINT uq_hf_job_reference_order UNIQUE (job_id, ordinal), \n\tCONSTRAINT uq_hf_job_reference_role UNIQUE (job_id, asset_version_id, media_role), \n\tCONSTRAINT ck_hf_job_reference_order CHECK (ordinal>=0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_job_reference IS '任务固定输入引用，不随素材更新漂移'")
    op.execute("COMMENT ON COLUMN hf_job_reference.reference_id IS '任务引用ID'")
    op.execute("COMMENT ON COLUMN hf_job_reference.job_id IS '所属生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_job_reference.asset_version_id IS '精确素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_job_reference.element_revision_id IS '元素修订来源ID'")
    op.execute("COMMENT ON COLUMN hf_job_reference.media_role IS '模型输入媒体角色'")
    op.execute("COMMENT ON COLUMN hf_job_reference.ordinal IS '编译顺序'")
    op.execute("COMMENT ON COLUMN hf_job_reference.reference_snapshot IS '授权与展示快照，不含签名地址'")
    op.execute("COMMENT ON COLUMN hf_job_reference.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_job_reference.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_job_reference.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_job_reference.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_task_event (\n\tevent_id BIGSERIAL NOT NULL, \n\tjob_id BIGINT NOT NULL, \n\tsequence BIGINT NOT NULL, \n\tevent_type VARCHAR(32) NOT NULL, \n\tschema_version INTEGER DEFAULT '1' NOT NULL, \n\tpayload JSONB NOT NULL, \n\toccurred_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (event_id), \n\tCONSTRAINT uq_hf_task_event_sequence UNIQUE (job_id, sequence), \n\tCONSTRAINT ck_hf_task_event_contract CHECK (sequence>0 AND schema_version>0 AND event_type IN ('task.state','output.state','chat.delta','chat.completed','usage.updated','task.problem'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_task_event IS '可重放持久任务事件，序号按任务事务分配'")
    op.execute("COMMENT ON COLUMN hf_task_event.event_id IS '任务事件ID'")
    op.execute("COMMENT ON COLUMN hf_task_event.job_id IS '所属生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_task_event.sequence IS '任务内提交事件序号，从一开始'")
    op.execute("COMMENT ON COLUMN hf_task_event.event_type IS '持久事件类别，不包含连接级消息'")
    op.execute("COMMENT ON COLUMN hf_task_event.schema_version IS '事件载荷结构版本'")
    op.execute("COMMENT ON COLUMN hf_task_event.payload IS '受控事件事实，不含秘密或临时签名地址'")
    op.execute("COMMENT ON COLUMN hf_task_event.occurred_time IS '事实发生时间，不作为排序键'")
    op.execute("COMMENT ON COLUMN hf_task_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_task_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_task_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_task_event.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_task_event_occurred ON hf_task_event (occurred_time)')
    op.execute(
        "CREATE TABLE hf_outbox_event (\n\tevent_id BIGSERIAL NOT NULL, \n\tevent_type VARCHAR(100) NOT NULL, \n\taggregate_type VARCHAR(100) NOT NULL, \n\taggregate_id BIGINT NOT NULL, \n\tpayload JSONB NOT NULL, \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\tnext_attempt_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tattempt_count INTEGER DEFAULT '0' NOT NULL, \n\tpublished_time TIMESTAMP(3) WITH TIME ZONE, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (event_id), \n\tCONSTRAINT ck_hf_outbox_state CHECK (state IN ('0','1') AND attempt_count>=0 AND ((state='0' AND published_time IS NULL) OR (state='1' AND published_time IS NOT NULL)))\n)"
    )
    op.execute("COMMENT ON TABLE hf_outbox_event IS '与业务写入同事务的待投递事件'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.event_id IS '事务事件唯一ID'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.event_type IS '事件类型'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.aggregate_type IS '所属业务聚合类别'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.aggregate_id IS '所属业务聚合ID'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.payload IS '资源引用及必要非秘密参数'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.state IS '状态：0待投递1已投递'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.next_attempt_time IS '下次投递时间'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.attempt_count IS '投递尝试次数'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.published_time IS '成功投递时间'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_outbox_event.update_time IS '更新时间'")
    op.execute("CREATE INDEX ix_hf_outbox_pending ON hf_outbox_event (next_attempt_time, event_id) WHERE state='0'")
    op.execute(
        "CREATE TABLE hf_processed_event (\n\tprocessed_id BIGSERIAL NOT NULL, \n\tconsumer_name VARCHAR(100) NOT NULL, \n\tevent_id BIGINT NOT NULL, \n\tprocessed_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (processed_id), \n\tCONSTRAINT uq_hf_processed_consumer_event UNIQUE (consumer_name, event_id)\n)"
    )
    op.execute("COMMENT ON TABLE hf_processed_event IS '消费者已完成事件去重，与处理结果同事务'")
    op.execute("COMMENT ON COLUMN hf_processed_event.processed_id IS '消费完成记录ID'")
    op.execute("COMMENT ON COLUMN hf_processed_event.consumer_name IS '消费者稳定名称'")
    op.execute("COMMENT ON COLUMN hf_processed_event.event_id IS '事务事件ID'")
    op.execute("COMMENT ON COLUMN hf_processed_event.processed_time IS '处理完成时间'")
    op.execute("COMMENT ON COLUMN hf_processed_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_processed_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_processed_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_processed_event.update_time IS '更新时间'")


def downgrade():
    op.execute('DROP TABLE hf_processed_event')
    op.execute('DROP TABLE hf_outbox_event')
    op.execute('DROP TABLE hf_task_event')
    op.execute('DROP TABLE hf_job_reference')
    op.execute('DROP TABLE hf_creation_job')

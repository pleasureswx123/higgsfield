"""供应商请求意图与运行事实的真实迁移。"""

from alembic import op

revision = '20261027_35'
down_revision = '20261027_34'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_provider_call (\n\tcall_id BIGSERIAL NOT NULL, \n\tjob_id BIGINT, \n\tcost_center_id BIGINT, \n\taccount_id BIGINT NOT NULL, \n\tcredential_version_id BIGINT NOT NULL, \n\toperation VARCHAR(32) NOT NULL, \n\trequest_hash CHAR(64) NOT NULL, \n\trequest_metadata JSONB NOT NULL, \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\tacceptance VARCHAR(32) DEFAULT 'unknown' NOT NULL, \n\thttp_status INTEGER, \n\tbusiness_code VARCHAR(100), \n\tresponse_metadata JSONB, \n\tresponse_id VARCHAR(255), \n\tactor_id BIGINT, \n\tstarted_time TIMESTAMP(3) WITH TIME ZONE, \n\tfinished_time TIMESTAMP(3) WITH TIME ZONE, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (call_id), \n\tCONSTRAINT ck_hf_call_subject CHECK ((job_id IS NOT NULL)<>(cost_center_id IS NOT NULL)), \n\tCONSTRAINT ck_hf_call_state CHECK (state IN ('0','1','2','3') AND acceptance IN ('accepted','rejected','unknown','not_applicable')), \n\tCONSTRAINT ck_hf_call_operation CHECK (operation IN ('chat','image','video_submit','video_poll','upload','register','asset_get','test')), \n\tCONSTRAINT ck_hf_call_metadata CHECK (request_hash ~ '^[0-9a-f]{64}$' AND jsonb_typeof(request_metadata)='object' AND (response_metadata IS NULL OR jsonb_typeof(response_metadata)='object')), \n\tCONSTRAINT ck_hf_call_http CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599), \n\tCONSTRAINT ck_hf_call_times CHECK ((state='0' AND started_time IS NULL AND finished_time IS NULL) OR (state='1' AND started_time IS NOT NULL AND finished_time IS NULL) OR (state IN ('2','3') AND started_time IS NOT NULL AND finished_time IS NOT NULL AND finished_time>=started_time)), \n\tCONSTRAINT ck_hf_call_acceptance CHECK (state NOT IN ('0','1','3') OR acceptance='unknown')\n)"
    )
    op.execute("COMMENT ON TABLE hf_provider_call IS '供应商真实请求意图及运行事实，不代表独立收费'")
    op.execute("COMMENT ON COLUMN hf_provider_call.call_id IS '外部调用ID'")
    op.execute("COMMENT ON COLUMN hf_provider_call.job_id IS '生成任务来源，与成本中心恰选其一'")
    op.execute("COMMENT ON COLUMN hf_provider_call.cost_center_id IS '非项目调用的成本中心ID'")
    op.execute("COMMENT ON COLUMN hf_provider_call.account_id IS '本次调用供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_provider_call.credential_version_id IS '本次实际凭据版本ID'")
    op.execute("COMMENT ON COLUMN hf_provider_call.operation IS '调用操作：对话图片视频提交轮询上传注册查询测试'")
    op.execute("COMMENT ON COLUMN hf_provider_call.request_hash IS '规范请求摘要，不存授权头'")
    op.execute("COMMENT ON COLUMN hf_provider_call.request_metadata IS '白名单脱敏请求及配置版本，不含秘密'")
    op.execute("COMMENT ON COLUMN hf_provider_call.state IS '状态：0计划1发送中2已完成3未知'")
    op.execute("COMMENT ON COLUMN hf_provider_call.acceptance IS '受理事实：accepted rejected unknown not_applicable'")
    op.execute("COMMENT ON COLUMN hf_provider_call.http_status IS '响应HTTP状态码，未收到为空'")
    op.execute("COMMENT ON COLUMN hf_provider_call.business_code IS '白名单供应商业务码'")
    op.execute("COMMENT ON COLUMN hf_provider_call.response_metadata IS '白名单脱敏响应，不含Base64或秘密URL'")
    op.execute("COMMENT ON COLUMN hf_provider_call.response_id IS '外层上游响应ID'")
    op.execute("COMMENT ON COLUMN hf_provider_call.actor_id IS '管理测试发起者，任务调用由任务追溯'")
    op.execute("COMMENT ON COLUMN hf_provider_call.started_time IS '开始发送时点'")
    op.execute("COMMENT ON COLUMN hf_provider_call.finished_time IS '响应记录或判定未知时点，不证明上游完成'")
    op.execute("COMMENT ON COLUMN hf_provider_call.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_call.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_call.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_call.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_call_account_created ON hf_provider_call (account_id, create_time)')
    op.execute('CREATE INDEX ix_hf_call_job_created ON hf_provider_call (job_id, create_time)')
    op.execute('CREATE INDEX ix_hf_call_state_started ON hf_provider_call (state, started_time)')


def downgrade():
    raise RuntimeError('供应商调用历史不可自动删除，请执行经审核的数据保留方案')

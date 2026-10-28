"""计费对象与不可变用量修订的固定DDL。"""

from alembic import op

revision = '20261027_38'
down_revision = '20261027_37'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE hf_billing_subject (\n\tsubject_id BIGSERIAL NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tjob_id BIGINT, \n\tcost_center_id BIGINT, \n\torigin_call_id BIGINT NOT NULL, \n\tsubject_kind VARCHAR(32) NOT NULL, \n\tprovider_object_id VARCHAR(255), \n\tidentity_key VARCHAR(255) NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (subject_id), \n\tCONSTRAINT ck_hf_billing_subject_owner CHECK ((job_id IS NULL) <> (cost_center_id IS NULL)), \n\tCONSTRAINT ck_hf_billing_subject_kind CHECK (subject_kind IN ('generation','test','registration','query_fee') AND length(identity_key)>0), \n\tCONSTRAINT uq_hf_billing_subject_local UNIQUE (account_id, subject_kind, identity_key), \n\tCONSTRAINT uq_hf_billing_subject_origin UNIQUE (origin_call_id, subject_kind)\n)\n\n"
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_billing_subject_provider ON hf_billing_subject (account_id, subject_kind, provider_object_id) WHERE provider_object_id IS NOT NULL'
    )
    op.execute("COMMENT ON TABLE hf_billing_subject IS '上游计费对象身份'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.subject_id IS '计费对象ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.account_id IS '供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.job_id IS '项目生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.cost_center_id IS '非项目消费归属ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.origin_call_id IS '原始调用ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.subject_kind IS '计费对象类型'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.provider_object_id IS '供应商计费对象ID'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.identity_key IS '稳定本地对象键'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_billing_subject.update_time IS '更新时间'")
    op.execute(
        "\nCREATE TABLE hf_usage_record (\n\tusage_id BIGSERIAL NOT NULL, \n\tsubject_id BIGINT NOT NULL, \n\tcall_id BIGINT NOT NULL, \n\trevision_no INTEGER NOT NULL, \n\tinput_tokens BIGINT, \n\toutput_tokens BIGINT, \n\tvideo_tokens BIGINT, \n\timage_count INTEGER, \n\toutput_seconds NUMERIC(18, 6), \n\treference_seconds NUMERIC(18, 6), \n\tcompleteness VARCHAR(32) NOT NULL, \n\tsource_path VARCHAR(200) NOT NULL, \n\tparser_version VARCHAR(100) NOT NULL, \n\tis_cumulative CHAR(1) NOT NULL, \n\tpayload_hash CHAR(64) NOT NULL, \n\traw_usage JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (usage_id), \n\tCONSTRAINT uq_hf_usage_revision UNIQUE (subject_id, revision_no), \n\tCONSTRAINT uq_hf_usage_payload UNIQUE (subject_id, payload_hash), \n\tCONSTRAINT ck_hf_usage_state CHECK (revision_no>0 AND completeness IN ('available','partial','unknown') AND is_cumulative IN ('Y','N')), \n\tCONSTRAINT ck_hf_usage_quantities CHECK (input_tokens>=0 AND output_tokens>=0 AND video_tokens>=0 AND image_count>=0 AND output_seconds>=0 AND reference_seconds>=0), \n\tCONSTRAINT ck_hf_usage_evidence CHECK (payload_hash ~ '^[a-f0-9]{64}$' AND jsonb_typeof(raw_usage)='object' AND length(source_path)>0 AND length(parser_version)>0)\n)\n\n"
    )
    op.execute("COMMENT ON TABLE hf_usage_record IS '原始及归一用量修订，不同修订不可求和'")
    op.execute("COMMENT ON COLUMN hf_usage_record.usage_id IS '用量修订ID'")
    op.execute("COMMENT ON COLUMN hf_usage_record.subject_id IS '计费对象ID'")
    op.execute("COMMENT ON COLUMN hf_usage_record.call_id IS '用量来源调用ID'")
    op.execute("COMMENT ON COLUMN hf_usage_record.revision_no IS '对象内用量修订序号'")
    op.execute("COMMENT ON COLUMN hf_usage_record.input_tokens IS '实际输入Token数，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.output_tokens IS '实际输出Token数，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.video_tokens IS '实际视频Token数，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.image_count IS '实际图片数量，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.output_seconds IS '实际输出时长秒，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.reference_seconds IS '实际参考时长秒，未知为空'")
    op.execute("COMMENT ON COLUMN hf_usage_record.completeness IS '用量完整性：available完整partial部分unknown未知'")
    op.execute("COMMENT ON COLUMN hf_usage_record.source_path IS '供应商用量字段路径'")
    op.execute("COMMENT ON COLUMN hf_usage_record.parser_version IS '用量归一规则版本'")
    op.execute("COMMENT ON COLUMN hf_usage_record.is_cumulative IS '是否累计：Y是N否'")
    op.execute("COMMENT ON COLUMN hf_usage_record.payload_hash IS '规范化用量证据SHA256摘要'")
    op.execute("COMMENT ON COLUMN hf_usage_record.raw_usage IS '白名单脱敏原始用量证据'")
    op.execute("COMMENT ON COLUMN hf_usage_record.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_usage_record.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_usage_record.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_usage_record.update_time IS '更新时间'")


def downgrade():
    raise RuntimeError('用量及计费对象历史不可自动删除，请执行经审核的数据保留方案')

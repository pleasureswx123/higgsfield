"""生成输出与独立归档状态。"""

from alembic import op

revision = '20261027_33'
down_revision = '20261027_32'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_generated_output (\n\toutput_id BIGSERIAL NOT NULL, \n\tjob_id BIGINT NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tfile_id BIGINT, \n\ttext_content TEXT, \n\tarchive_state CHAR(1) DEFAULT '0' NOT NULL, \n\tsource_url_ciphertext BYTEA, \n\tsource_expires_time TIMESTAMP(3) WITH TIME ZONE, \n\tactual_metadata JSONB DEFAULT '{}'::jsonb NOT NULL, \n\tnext_retry_time TIMESTAMP(3) WITH TIME ZONE, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\twork_status CHAR(1) DEFAULT '0' NOT NULL, \n\tdel_flag CHAR(1) DEFAULT '0' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (output_id), \n\tCONSTRAINT uq_hf_output_job_ordinal UNIQUE (job_id, ordinal), \n\tCONSTRAINT ck_hf_output_states CHECK (ordinal>=0 AND revision>0 AND kind IN ('image','video','text') AND archive_state IN ('0','1','2','3','4','5') AND work_status IN ('0','1','2','3','4') AND del_flag IN ('0','2')), \n\tCONSTRAINT ck_hf_output_content CHECK ((kind='text' AND text_content IS NOT NULL AND length(text_content)>0 AND archive_state='5' AND file_id IS NULL AND source_url_ciphertext IS NULL) OR (kind IN ('image','video') AND text_content IS NULL AND archive_state<>'5')), \n\tCONSTRAINT ck_hf_output_archived_file CHECK ((archive_state='2')=(file_id IS NOT NULL)), \n\tCONSTRAINT ck_hf_output_metadata CHECK (jsonb_typeof(actual_metadata)='object')\n)"
    )
    op.execute("COMMENT ON TABLE hf_generated_output IS '生成输出及独立归档状态'")
    op.execute("COMMENT ON COLUMN hf_generated_output.output_id IS '生成输出ID'")
    op.execute("COMMENT ON COLUMN hf_generated_output.job_id IS '所属生成任务ID'")
    op.execute("COMMENT ON COLUMN hf_generated_output.ordinal IS '供应商输出序号，从零开始'")
    op.execute("COMMENT ON COLUMN hf_generated_output.kind IS '输出类型：图片、视频或文本'")
    op.execute("COMMENT ON COLUMN hf_generated_output.file_id IS '成功归档的固定文件ID'")
    op.execute("COMMENT ON COLUMN hf_generated_output.text_content IS '文本输出正文，非文本为空'")
    op.execute(
        "COMMENT ON COLUMN hf_generated_output.archive_state IS '归档：0未开始1归档中2已归档3失败4源过期5不适用'"
    )
    op.execute(
        "COMMENT ON COLUMN hf_generated_output.source_url_ciphertext IS '临时地址加密封装，包含密钥版本、随机数和认证标签'"
    )
    op.execute("COMMENT ON COLUMN hf_generated_output.source_expires_time IS '临时源地址到期时间'")
    op.execute(
        "COMMENT ON COLUMN hf_generated_output.actual_metadata IS '受控实际尺寸时长格式及优化提示词，不含秘密地址'"
    )
    op.execute("COMMENT ON COLUMN hf_generated_output.next_retry_time IS '下次归档调度时间'")
    op.execute("COMMENT ON COLUMN hf_generated_output.revision IS '输出并发版本'")
    op.execute("COMMENT ON COLUMN hf_generated_output.work_status IS '工作状态：0无1制作中2待审核3已通过4已拒绝'")
    op.execute("COMMENT ON COLUMN hf_generated_output.del_flag IS '删除标志：0存在2删除'")
    op.execute("COMMENT ON COLUMN hf_generated_output.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_generated_output.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_generated_output.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_generated_output.update_time IS '更新时间'")
    op.execute(
        "CREATE INDEX ix_hf_output_archive_retry ON hf_generated_output (archive_state, next_retry_time) WHERE archive_state IN ('3','0') AND del_flag='0'"
    )


def downgrade():
    op.drop_table('hf_generated_output')

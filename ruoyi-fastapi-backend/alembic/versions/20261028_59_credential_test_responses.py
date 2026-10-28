"""凭据测试原始响应索引，保留业务任务响应结构。"""
from alembic import op
revision = '20261028_59'
down_revision = '20261028_58'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("\nCREATE TABLE hf_credential_test_response (\n\tresponse_evidence_id BIGSERIAL NOT NULL, \n\ttest_id BIGINT NOT NULL, \n\tprovider_call_id BIGINT NOT NULL, \n\tstorage_key VARCHAR(100) NOT NULL, \n\tsha256 VARCHAR(64) NOT NULL, \n\tbyte_size BIGINT NOT NULL, \n\thttp_status INTEGER NOT NULL, \n\tformat_version INTEGER DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (response_evidence_id), \n\tCONSTRAINT uq_hf_test_response_test UNIQUE (test_id), \n\tCONSTRAINT uq_hf_test_response_call UNIQUE (provider_call_id), \n\tCONSTRAINT uq_hf_test_response_key UNIQUE (storage_key), \n\tCONSTRAINT ck_hf_test_response_values CHECK (test_id>0 AND provider_call_id>0 AND byte_size>0 AND http_status BETWEEN 100 AND 599 AND format_version=1), \n\tCONSTRAINT ck_hf_test_response_file CHECK (storage_key ~ '^provider-evidence/[a-f0-9]{32}$' AND sha256 ~ '^[a-f0-9]{64}$')\n)\n\n")
    op.execute("COMMENT ON TABLE hf_credential_test_response IS '凭据测试不可变响应证据索引'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.response_evidence_id IS '测试响应证据ID'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.test_id IS '原始凭据测试ID'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.provider_call_id IS '原始测试供应商调用ID'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.storage_key IS '受控加密证据文件定位键'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.sha256 IS '加密文件SHA256摘要'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.byte_size IS '加密文件字节数'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.http_status IS '供应商HTTP响应状态码'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.format_version IS '证据封装版本'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_credential_test_response.update_time IS '更新时间'")


def downgrade():
    raise RuntimeError("测试响应证据不可自动删除，请执行经审核的数据保留方案")

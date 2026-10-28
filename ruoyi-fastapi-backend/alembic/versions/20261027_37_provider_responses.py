"""供应商响应加密文件证据索引，不可自动删除历史。"""

from alembic import op

revision = '20261027_37'
down_revision = '20261027_36'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE hf_provider_response (
            response_evidence_id BIGSERIAL PRIMARY KEY,
            provider_call_id BIGINT NOT NULL,
            job_id BIGINT NOT NULL,
            storage_key VARCHAR(100) NOT NULL,
            sha256 VARCHAR(64) NOT NULL,
            byte_size BIGINT NOT NULL,
            http_status INTEGER NOT NULL,
            format_version INTEGER NOT NULL DEFAULT 1,
            create_by VARCHAR(64) NOT NULL DEFAULT '',
            update_by VARCHAR(64) NOT NULL DEFAULT '',
            create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL,
            update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_hf_provider_response_call UNIQUE(provider_call_id),
            CONSTRAINT uq_hf_provider_response_key UNIQUE(storage_key),
            CONSTRAINT ck_hf_provider_response_values CHECK(byte_size>0 AND http_status BETWEEN 100 AND 599 AND format_version=1),
            CONSTRAINT ck_hf_provider_response_file CHECK(storage_key ~ '^provider-evidence/[a-f0-9]{32}$' AND sha256 ~ '^[a-f0-9]{64}$')
        )
    """)
    op.execute("COMMENT ON TABLE hf_provider_response IS '不可变供应商响应证据索引'")
    comments = {
        'response_evidence_id': '响应证据ID',
        'provider_call_id': '原始供应商调用ID',
        'job_id': '原始生成任务ID',
        'storage_key': '受控加密证据文件定位键',
        'sha256': '加密文件SHA256摘要',
        'byte_size': '加密文件字节数',
        'http_status': '供应商HTTP响应状态码',
        'format_version': '证据封装版本',
        'create_by': '创建者',
        'update_by': '更新者',
        'create_time': '创建时间',
        'update_time': '更新时间',
    }
    for column, comment in comments.items():
        op.execute(f"COMMENT ON COLUMN hf_provider_response.{column} IS '{comment}'")


def downgrade():
    raise RuntimeError('响应历史证据不可自动删除，请执行经审核的数据保留方案')

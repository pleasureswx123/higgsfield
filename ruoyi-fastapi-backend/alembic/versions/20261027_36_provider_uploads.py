"""外部临时上传与加密地址事实表，保留过期历史。"""

from alembic import op

revision = '20261027_36'
down_revision = '20261027_35'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE hf_provider_upload (\n\tprovider_upload_id BIGSERIAL NOT NULL, \n\tasset_version_id BIGINT NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tcredential_version_id BIGINT NOT NULL, \n\tprovider_call_id BIGINT NOT NULL, \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\turl_ciphertext BYTEA, \n\texpires_time TIMESTAMP(3) WITH TIME ZONE, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (provider_upload_id), \n\tCONSTRAINT uq_hf_provider_upload_call UNIQUE (provider_call_id), \n\tCONSTRAINT ck_hf_provider_upload_state CHECK (state IN ('0','1','2','3','4')), \n\tCONSTRAINT ck_hf_provider_upload_source CHECK ((state IN ('1','4') AND url_ciphertext IS NOT NULL AND expires_time IS NOT NULL AND expires_time>create_time) OR (state IN ('0','2','3') AND url_ciphertext IS NULL AND expires_time IS NULL))\n)\n\n"
    )
    op.execute("COMMENT ON TABLE hf_provider_upload IS '外部临时上传及加密地址，不替代平台长期文件'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.provider_upload_id IS '外部临时上传ID'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.asset_version_id IS '固定源素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.account_id IS '供应商账号范围ID'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.credential_version_id IS '本次上传原始凭据版本ID'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.provider_call_id IS '本次上传调用事实ID'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.state IS '状态：0上传中1可用2失败3未知4过期'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.url_ciphertext IS '绑定上传身份和原凭据的加密临时URL'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.expires_time IS '已扣除安全余量的到期时间'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_upload.update_time IS '更新时间'")
    op.execute(
        'CREATE INDEX ix_hf_provider_upload_reuse ON hf_provider_upload (asset_version_id, account_id, credential_version_id, expires_time DESC)'
    )


def downgrade():
    raise RuntimeError('外部上传事实不可自动删除，请执行经审核的数据保留方案')

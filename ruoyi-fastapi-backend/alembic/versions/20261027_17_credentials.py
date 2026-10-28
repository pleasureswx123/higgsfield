"""凭据身份与认证加密版本，不植入秘密或自动启用。"""

from alembic import op

revision = '20261027_17'
down_revision = '20261027_16'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_provider_credential (\n\tcredential_id BIGSERIAL NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tcredential_name VARCHAR(200) NOT NULL, \n\towner_id BIGINT NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (credential_id), \n\tCONSTRAINT uq_hf_credential_name UNIQUE (account_id, credential_name), \n\tCONSTRAINT uq_hf_credential_account UNIQUE (credential_id, account_id), \n\tCONSTRAINT ck_hf_credential_state CHECK (status IN ('0','1','2','3','4') AND revision>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_provider_credential IS '供应商凭据身份，不含密钥明文'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.credential_id IS '凭据身份ID'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.account_id IS '所属供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.credential_name IS '凭据管理名称'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.owner_id IS '责任人用户ID'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.status IS '状态：0草稿1启用2排空3停用4撤销'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.revision IS '元数据并发版本'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_credential.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_credential_version (\n\tcredential_version_id BIGSERIAL NOT NULL, \n\tcredential_id BIGINT NOT NULL, \n\tconnection_version_id BIGINT NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tsecret_ciphertext BYTEA NOT NULL, \n\tnonce BYTEA NOT NULL, \n\tauth_tag BYTEA NOT NULL, \n\tmaster_key_version VARCHAR(100) NOT NULL, \n\tfingerprint VARCHAR(128) NOT NULL, \n\tmasked_suffix VARCHAR(8) NOT NULL, \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\tvalid_from TIMESTAMP WITH TIME ZONE NOT NULL, \n\tvalid_until TIMESTAMP WITH TIME ZONE, \n\trevoked_time TIMESTAMP WITH TIME ZONE, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (credential_version_id), \n\tCONSTRAINT uq_hf_credential_version_no UNIQUE (credential_id, version_no), \n\tCONSTRAINT uq_hf_credential_nonce UNIQUE (master_key_version, nonce), \n\tCONSTRAINT ck_hf_credential_version_state CHECK (state IN ('0','1','2','3','4') AND revision>0 AND version_no>0), \n\tCONSTRAINT ck_hf_credential_encryption CHECK (octet_length(nonce)=12 AND octet_length(auth_tag)=16 AND octet_length(secret_ciphertext)>0), \n\tCONSTRAINT ck_hf_credential_validity CHECK (valid_until IS NULL OR valid_until>valid_from)\n)"
    )
    op.execute("COMMENT ON TABLE hf_credential_version IS '绑定配置的加密供应商密钥版本'")
    op.execute("COMMENT ON COLUMN hf_credential_version.credential_version_id IS '加密凭据版本ID'")
    op.execute("COMMENT ON COLUMN hf_credential_version.credential_id IS '凭据身份ID'")
    op.execute("COMMENT ON COLUMN hf_credential_version.connection_version_id IS '固定供应商连接配置版本ID'")
    op.execute("COMMENT ON COLUMN hf_credential_version.version_no IS '凭据内部版本号'")
    op.execute("COMMENT ON COLUMN hf_credential_version.secret_ciphertext IS '认证加密后的密文，不向管理员返回'")
    op.execute("COMMENT ON COLUMN hf_credential_version.nonce IS '十二字节随机数，同主密钥版本唯一'")
    op.execute("COMMENT ON COLUMN hf_credential_version.auth_tag IS '十六字节认证标签'")
    op.execute("COMMENT ON COLUMN hf_credential_version.master_key_version IS '运行时主密钥版本，主密钥不入库'")
    op.execute("COMMENT ON COLUMN hf_credential_version.fingerprint IS '带密钥摘要指纹，仅用于内部匹配'")
    op.execute("COMMENT ON COLUMN hf_credential_version.masked_suffix IS '掩码及末尾四字符'")
    op.execute("COMMENT ON COLUMN hf_credential_version.state IS '状态：0草稿1启用2排空3停用4撤销'")
    op.execute("COMMENT ON COLUMN hf_credential_version.valid_from IS '有效期起点'")
    op.execute("COMMENT ON COLUMN hf_credential_version.valid_until IS '有效期终点'")
    op.execute("COMMENT ON COLUMN hf_credential_version.revoked_time IS '撤销时间'")
    op.execute("COMMENT ON COLUMN hf_credential_version.revision IS '状态并发版本'")
    op.execute("COMMENT ON COLUMN hf_credential_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_credential_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_credential_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_credential_version.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_credential_version_state ON hf_credential_version (credential_id, state)')


def downgrade():
    raise RuntimeError('历史凭据版本不可自动删除')

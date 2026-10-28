"""供应商账号和上游项目作用域。"""

from alembic import op

revision = '20261027_15'
down_revision = '20261027_14'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_provider_account (\n\taccount_id BIGSERIAL NOT NULL, \n\tconnection_id BIGINT NOT NULL, \n\taccount_code VARCHAR(100) NOT NULL, \n\tregion VARCHAR(32) NOT NULL, \n\tupstream_project VARCHAR(100) NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (account_id), \n\tCONSTRAINT uq_hf_provider_account_scope UNIQUE (connection_id, account_code, region, upstream_project), \n\tCONSTRAINT uq_hf_provider_account_connection UNIQUE (account_id, connection_id), \n\tCONSTRAINT ck_hf_provider_account_status CHECK (status IN ('0','1'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_provider_account IS '供应商账号及素材作用域'")
    op.execute("COMMENT ON COLUMN hf_provider_account.account_id IS '供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_provider_account.connection_id IS '所属供应商连接ID'")
    op.execute("COMMENT ON COLUMN hf_provider_account.account_code IS '公司登记的供应商账号编码'")
    op.execute("COMMENT ON COLUMN hf_provider_account.region IS '明确的供应商区域作用域'")
    op.execute("COMMENT ON COLUMN hf_provider_account.upstream_project IS '供应商侧项目标识，不以业务项目名代替'")
    op.execute("COMMENT ON COLUMN hf_provider_account.status IS '状态：0正常1停用'")
    op.execute("COMMENT ON COLUMN hf_provider_account.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_account.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_account.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_account.update_time IS '更新时间'")


def downgrade():
    raise RuntimeError('供应商账号身份不可自动删除')

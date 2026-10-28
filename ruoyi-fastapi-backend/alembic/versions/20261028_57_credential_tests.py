"""创建凭据测试证据表，固定配置、操作者与管理消费归属。"""
from alembic import op
revision = '20261028_57'
down_revision = '20261028_56'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_credential_test (
        test_id bigserial PRIMARY KEY, credential_version_id bigint NOT NULL,
        connection_version_id bigint NOT NULL, config_hash char(64) NOT NULL,
        model_version_id bigint, cost_center_id bigint NOT NULL, requested_by bigint NOT NULL,
        state char(1) NOT NULL DEFAULT '0', provider_call_id bigint, finished_time timestamptz(3),
        result jsonb NOT NULL,
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT ck_hf_credential_test_hash CHECK(config_hash ~ '^[0-9a-f]{64}$'),
        CONSTRAINT ck_hf_credential_test_result CHECK(jsonb_typeof(result)='object'),
        CONSTRAINT ck_hf_credential_test_state CHECK(state IN ('0','1','2') AND
            ((state='0' AND finished_time IS NULL) OR (state IN ('1','2') AND finished_time IS NOT NULL))),
        CONSTRAINT ck_hf_credential_test_passed_call CHECK(state<>'1' OR provider_call_id IS NOT NULL),
        CONSTRAINT ck_hf_credential_test_identity CHECK(credential_version_id>0 AND connection_version_id>0 AND cost_center_id>0 AND requested_by>0)
    )""")
    op.execute('CREATE INDEX ix_hf_credential_test_version ON hf_credential_test(credential_version_id,create_time)')
    op.execute('CREATE INDEX ix_hf_credential_test_pending ON hf_credential_test(state,create_time)')
    op.execute("COMMENT ON TABLE hf_credential_test IS '绑定精确配置的凭据测试及非项目消费证据'")
    for column, comment in {
        'test_id': '凭据测试ID', 'credential_version_id': '被测凭据版本ID',
        'connection_version_id': '固定连接配置版本ID', 'config_hash': '完整测试配置摘要',
        'model_version_id': '被测模型能力版本ID，非模型测试为空', 'cost_center_id': '管理消费归属成本中心ID',
        'requested_by': '发起测试的用户ID', 'state': '测试状态：0待执行1通过2失败',
        'provider_call_id': '真实测试调用ID，未发送为空', 'finished_time': '测试完成时间',
        'result': '脱敏诊断事实，不含秘密或原始响应', 'create_by': '创建者', 'update_by': '更新者',
        'create_time': '创建时间', 'update_time': '更新时间',
    }.items():
        op.execute(f"COMMENT ON COLUMN hf_credential_test.{column} IS '{comment}'")


def downgrade():
    raise RuntimeError('测试证据可能已被启用和账本引用，不自动删除')

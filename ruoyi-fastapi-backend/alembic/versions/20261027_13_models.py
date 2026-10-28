"""模型身份、能力版本、精确规格及供应商连接身份。"""

from alembic import op

revision = '20261027_13'
down_revision = '20261027_12'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_provider_connection (\n\tconnection_id BIGSERIAL NOT NULL, \n\tconnection_name VARCHAR(200) NOT NULL, \n\tenvironment VARCHAR(32) NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\tcurrent_version_id BIGINT, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (connection_id), \n\tCONSTRAINT uq_hf_connection_name UNIQUE (environment, connection_name), \n\tCONSTRAINT ck_hf_connection_state CHECK (environment IN ('test','production') AND status IN ('0','1','2') AND revision>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_provider_connection IS '供应商连接身份'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.connection_id IS '连接ID'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.connection_name IS '连接名称'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.environment IS '测试或正式环境'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.status IS '状态：0草稿1启用2停用'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.current_version_id IS '当前连接配置版本ID'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_connection.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_model_profile (\n\tmodel_id BIGSERIAL NOT NULL, \n\tconnection_id BIGINT NOT NULL, \n\tcode VARCHAR(100) NOT NULL, \n\tdisplay_name VARCHAR(200) NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (model_id), \n\tCONSTRAINT uq_hf_model_code UNIQUE (connection_id, code), \n\tCONSTRAINT ck_hf_model_kind CHECK (kind IN ('chat','image','video'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_model_profile IS '模型能力身份'")
    op.execute("COMMENT ON COLUMN hf_model_profile.model_id IS '模型ID'")
    op.execute("COMMENT ON COLUMN hf_model_profile.connection_id IS '供应商连接ID'")
    op.execute("COMMENT ON COLUMN hf_model_profile.code IS '平台稳定模型码'")
    op.execute("COMMENT ON COLUMN hf_model_profile.display_name IS '模型展示名称'")
    op.execute("COMMENT ON COLUMN hf_model_profile.kind IS '模型任务类型'")
    op.execute("COMMENT ON COLUMN hf_model_profile.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_model_profile.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_model_profile.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_model_profile.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_model_profile_version (\n\tmodel_version_id BIGSERIAL NOT NULL, \n\tmodel_id BIGINT NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tgateway_alias VARCHAR(100) NOT NULL, \n\tunderlying_model_id VARCHAR(255), \n\tregion VARCHAR(32) NOT NULL, \n\tcapabilities JSONB NOT NULL, \n\tschema_version INTEGER DEFAULT '1' NOT NULL, \n\tstatus CHAR(1) DEFAULT '0' NOT NULL, \n\tverification_ref TEXT, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (model_version_id), \n\tCONSTRAINT uq_hf_model_version_no UNIQUE (model_id, version_no), \n\tCONSTRAINT uq_hf_model_version_identity UNIQUE (model_id, model_version_id), \n\tCONSTRAINT ck_hf_model_version_state CHECK (version_no>0 AND schema_version=1 AND revision>0 AND status IN ('0','1','2','3'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_model_profile_version IS '模型不可变能力版本'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.model_version_id IS '能力版本ID'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.model_id IS '模型身份ID'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.version_no IS '模型内部版本号'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.gateway_alias IS '精确上游调用别名'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.underlying_model_id IS '已确认底层版本标识，未知为空'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.region IS '账号及素材区域作用域'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.capabilities IS '白名单模型能力配置'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.schema_version IS '能力结构契约版本'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.status IS '状态：0草稿1已验证2已发布3停用'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.verification_ref IS '已审阅的脱敏联调证据位置'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_model_profile_version.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_model_variant (\n\tvariant_id BIGSERIAL NOT NULL, \n\tmodel_version_id BIGINT NOT NULL, \n\tvariant_key VARCHAR(200) NOT NULL, \n\tdimensions JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (variant_id), \n\tCONSTRAINT uq_hf_model_variant_key UNIQUE (model_version_id, variant_key), \n\tCONSTRAINT uq_hf_model_variant_identity UNIQUE (variant_id, model_version_id)\n)"
    )
    op.execute("COMMENT ON TABLE hf_model_variant IS '模型精确计价规格'")
    op.execute("COMMENT ON COLUMN hf_model_variant.variant_id IS '规格ID'")
    op.execute("COMMENT ON COLUMN hf_model_variant.model_version_id IS '所属能力版本ID'")
    op.execute("COMMENT ON COLUMN hf_model_variant.variant_key IS '规范化完整条件摘要键'")
    op.execute("COMMENT ON COLUMN hf_model_variant.dimensions IS '完整计价条件，不允许通配符'")
    op.execute("COMMENT ON COLUMN hf_model_variant.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_model_variant.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_model_variant.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_model_variant.update_time IS '更新时间'")
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '读取模型能力',menu_id,10,'','F','1','0','model:read','migration_hf_13',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='model:read')"
    )
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '编辑模型能力',menu_id,10,'','F','1','0','model:write','migration_hf_13',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='model:write')"
    )


def downgrade():
    raise RuntimeError('模型版本和配置证据不可回退删除')

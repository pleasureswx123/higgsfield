"""不可变供应商连接配置版本。"""

from alembic import op

revision = '20261027_14'
down_revision = '20261027_13'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_provider_connection_version (\n\tconnection_version_id BIGSERIAL NOT NULL, \n\tconnection_id BIGINT NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tbase_url TEXT NOT NULL, \n\tadapter_version VARCHAR(100) NOT NULL, \n\tconfig JSONB NOT NULL, \n\tconfig_hash CHAR(64) NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (connection_version_id), \n\tCONSTRAINT uq_hf_connection_version_no UNIQUE (connection_id, version_no), \n\tCONSTRAINT uq_hf_connection_version_identity UNIQUE (connection_id, connection_version_id), \n\tCONSTRAINT ck_hf_connection_version_no CHECK (version_no>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_provider_connection_version IS '不可变供应商连接配置版本'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.connection_version_id IS '连接配置版本ID'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.connection_id IS '所属连接身份ID'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.version_no IS '内部配置版本号'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.base_url IS '登记的供应商地址，不代表已通过传输验证'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.adapter_version IS '固定适配器版本'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.config IS '白名单非秘密配置'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.config_hash IS '地址适配器及配置规范化摘要'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_provider_connection_version.update_time IS '更新时间'")
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '读取供应商连接',menu_id,11,'','F','1','0','provider:read','migration_hf_14',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='provider:read')"
    )
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '编辑供应商连接',menu_id,11,'','F','1','0','provider:write','migration_hf_14',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='provider:write')"
    )


def downgrade():
    raise RuntimeError('连接配置版本不可自动删除')

"""项目整组模型路由、显式账号与候选凭据。"""

from alembic import op

revision = '20261027_21'
down_revision = '20261027_20'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '配置项目模型路由',menu_id,14,'','F','1','0','provider:route','migration_hf_21',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='provider:route')"
    )
    op.execute(
        "CREATE TABLE hf_project_routing_set (\n\trouting_set_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (routing_set_id), \n\tCONSTRAINT uq_hf_routing_set_project UNIQUE (project_id), \n\tCONSTRAINT ck_hf_routing_set_revision CHECK (revision>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_project_routing_set IS '项目整组模型路由并发版本'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.routing_set_id IS '路由组ID'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.project_id IS '所属项目ID，一个项目一组'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.revision IS '整组并发版本'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_project_routing_set.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_project_provider_config (\n\tconfig_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT NOT NULL, \n\tmodel_id BIGINT NOT NULL, \n\taccount_id BIGINT NOT NULL, \n\tstatus CHAR(1) DEFAULT '1' NOT NULL, \n\tpriority INTEGER DEFAULT '100' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (config_id), \n\tCONSTRAINT uq_hf_project_model_account UNIQUE (project_id, model_id, account_id), \n\tCONSTRAINT ck_hf_project_route CHECK (status IN ('0','1') AND priority>=0 AND revision>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_project_provider_config IS '项目模型到供应商账号的显式路由'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.config_id IS '项目路由配置ID'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.project_id IS '所属项目及路由组ID'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.model_id IS '模型身份ID'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.account_id IS '供应商账号ID'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.status IS '状态：0启用1停用'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.priority IS '路由优先级，数值越小越优先'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.revision IS '路由内部修订号'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_project_provider_config.update_time IS '更新时间'")
    op.execute(
        'CREATE INDEX ix_hf_project_route_priority ON hf_project_provider_config (project_id, model_id, status, priority)'
    )
    op.execute(
        "CREATE TABLE hf_routing_policy (\n\tpolicy_id BIGSERIAL NOT NULL, \n\tproject_provider_config_id BIGINT NOT NULL, \n\tcredential_id BIGINT NOT NULL, \n\tpriority INTEGER DEFAULT '100' NOT NULL, \n\tmax_concurrency INTEGER NOT NULL, \n\tenabled CHAR(1) DEFAULT 'N' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (policy_id), \n\tCONSTRAINT uq_hf_route_credential UNIQUE (project_provider_config_id, credential_id), \n\tCONSTRAINT ck_hf_routing_policy CHECK (priority>=0 AND max_concurrency>0 AND enabled IN ('Y','N'))\n)"
    )
    op.execute("COMMENT ON TABLE hf_routing_policy IS '项目显式路由候选凭据及并发上限'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.policy_id IS '路由凭据候选ID'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.project_provider_config_id IS '项目路由配置ID'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.credential_id IS '候选凭据身份ID'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.priority IS '凭据优先级，数值越小越优先'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.max_concurrency IS '候选凭据最大并发数'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.enabled IS '是否启用：Y是N否'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_routing_policy.update_time IS '更新时间'")
    op.execute(
        'INSERT INTO hf_project_routing_set (project_id,revision,create_by,update_by,create_time,update_time) SELECT project_id,1,create_by,update_by,create_time,update_time FROM hf_project'
    )


def downgrade():
    raise RuntimeError('项目路由与审计关联不可自动删除')

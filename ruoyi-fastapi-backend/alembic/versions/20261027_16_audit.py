"""模型治理权限及只追加业务审计。"""

from alembic import op

revision = '20261027_16'
down_revision = '20261027_15'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_audit_log (\n\taudit_id BIGSERIAL NOT NULL, \n\tactor_id BIGINT, \n\tactor_kind VARCHAR(32) NOT NULL, \n\tproject_id BIGINT, \n\tobject_type VARCHAR(100) NOT NULL, \n\tobject_id VARCHAR(255) NOT NULL, \n\taction VARCHAR(100) NOT NULL, \n\trequest_id VARCHAR(100) NOT NULL, \n\tbefore_after JSONB NOT NULL, \n\treason TEXT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (audit_id), \n\tCONSTRAINT ck_hf_audit_actor CHECK (actor_kind IN ('user','system') AND (actor_kind<>'user' OR actor_id IS NOT NULL))\n)"
    )
    op.execute("COMMENT ON TABLE hf_audit_log IS '只追加业务审计记录'")
    op.execute("COMMENT ON COLUMN hf_audit_log.audit_id IS '审计记录ID'")
    op.execute("COMMENT ON COLUMN hf_audit_log.actor_id IS '操作者用户ID'")
    op.execute("COMMENT ON COLUMN hf_audit_log.actor_kind IS '操作者类别'")
    op.execute("COMMENT ON COLUMN hf_audit_log.project_id IS '所属业务项目ID'")
    op.execute("COMMENT ON COLUMN hf_audit_log.object_type IS '审计对象类型'")
    op.execute("COMMENT ON COLUMN hf_audit_log.object_id IS '历史对象定位标识'")
    op.execute("COMMENT ON COLUMN hf_audit_log.action IS '受控操作名称'")
    op.execute("COMMENT ON COLUMN hf_audit_log.request_id IS '关联请求摘要标识'")
    op.execute("COMMENT ON COLUMN hf_audit_log.before_after IS '操作前后非秘密白名单事实'")
    op.execute("COMMENT ON COLUMN hf_audit_log.reason IS '敏感操作原因'")
    op.execute("COMMENT ON COLUMN hf_audit_log.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_audit_log.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_audit_log.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_audit_log.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_audit_actor ON hf_audit_log (actor_id, create_time)')
    op.execute('CREATE INDEX ix_hf_audit_object ON hf_audit_log (object_type, object_id, create_time)')
    op.execute('CREATE INDEX ix_hf_audit_project ON hf_audit_log (project_id, create_time, audit_id)')
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '审核模型验证证据',menu_id,12,'','F','1','0','model:verify','migration_hf_16',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='model:verify')"
    )
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '发布停用模型能力',menu_id,12,'','F','1','0','model:publish','migration_hf_16',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='model:publish')"
    )


def downgrade():
    raise RuntimeError('业务审计不可删除')

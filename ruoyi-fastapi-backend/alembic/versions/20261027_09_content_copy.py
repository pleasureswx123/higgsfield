"""固定复制来源证据与媒体使用功能码。"""

from alembic import op

revision = '20261027_09'
down_revision = '20261027_08'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_content_copy (\n\tcopy_id BIGSERIAL NOT NULL, \n\ttarget_kind VARCHAR(16) NOT NULL, \n\tsource_project_id BIGINT NOT NULL, \n\tsource_version_id BIGINT NOT NULL, \n\ttarget_project_id BIGINT NOT NULL, \n\ttarget_version_id BIGINT NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (copy_id), \n\tCONSTRAINT ck_hf_copy_kind CHECK (target_kind IN ('element','asset')), \n\tCONSTRAINT uq_hf_copy_target UNIQUE (target_kind, target_version_id)\n)"
    )
    op.execute("COMMENT ON TABLE hf_content_copy IS '受控复制固定版本来源证据'")
    op.execute("COMMENT ON COLUMN hf_content_copy.copy_id IS '复制证据ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.target_kind IS '复制对象类型'")
    op.execute("COMMENT ON COLUMN hf_content_copy.source_project_id IS '来源项目ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.source_version_id IS '来源素材版本或元素修订ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.target_project_id IS '目标项目ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.target_version_id IS '目标素材版本或元素修订ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.actor_id IS '复制操作者用户ID'")
    op.execute("COMMENT ON COLUMN hf_content_copy.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_content_copy.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_content_copy.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_content_copy.update_time IS '更新时间'")
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '使用项目媒体',menu_id,7,'','F','1','0','asset:reference','migration_hf_09',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='asset:reference')"
    )


def downgrade():
    raise RuntimeError('复制来源证据不可回退删除')

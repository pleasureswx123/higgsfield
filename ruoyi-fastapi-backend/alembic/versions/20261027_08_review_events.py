"""内容状态变更审计事件。"""

from alembic import op

revision = '20261027_08'
down_revision = '20261027_07'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_review_event (\n\treview_event_id BIGSERIAL NOT NULL, \n\telement_id BIGINT, \n\toutput_id BIGINT, \n\tactor_id BIGINT NOT NULL, \n\tfrom_status VARCHAR(32) NOT NULL, \n\tto_status VARCHAR(32) NOT NULL, \n\treason TEXT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (review_event_id), \n\tCONSTRAINT ck_hf_review_target CHECK (num_nonnulls(element_id,output_id)=1), \n\tCONSTRAINT ck_hf_review_status CHECK (from_status IN ('none','working','review','approved','rejected') AND to_status IN ('none','working','review','approved','rejected') AND from_status != to_status)\n)"
    )
    op.execute('CREATE INDEX ix_hf_review_element ON hf_review_event (element_id, create_time)')
    op.execute('CREATE INDEX ix_hf_review_output ON hf_review_event (output_id, create_time)')
    op.execute("COMMENT ON TABLE hf_review_event IS '内容工作状态变更历史'")
    op.execute("COMMENT ON COLUMN hf_review_event.review_event_id IS '状态事件ID'")
    op.execute("COMMENT ON COLUMN hf_review_event.element_id IS '元素目标ID'")
    op.execute("COMMENT ON COLUMN hf_review_event.output_id IS '生成作品目标ID'")
    op.execute("COMMENT ON COLUMN hf_review_event.actor_id IS '操作者用户ID'")
    op.execute("COMMENT ON COLUMN hf_review_event.from_status IS '变更前工作状态'")
    op.execute("COMMENT ON COLUMN hf_review_event.to_status IS '变更后工作状态'")
    op.execute("COMMENT ON COLUMN hf_review_event.reason IS '变更说明'")
    op.execute("COMMENT ON COLUMN hf_review_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_review_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_review_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_review_event.update_time IS '更新时间'")
    op.execute(
        "INSERT INTO sys_menu (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '审核内容工作状态',menu_id,6,'','F','1','0','content:review','migration_hf_08',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='content:review')"
    )


def downgrade():
    raise RuntimeError('状态审计事件不可回退删除')

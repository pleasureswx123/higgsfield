"""价格生效区间、发布历史及发布权限。"""

from alembic import op

revision = '20261027_25'
down_revision = '20261027_24'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_price_activation (\n\tactivation_id BIGSERIAL NOT NULL, \n\tprice_book_id BIGINT NOT NULL, \n\tprice_version_id BIGINT NOT NULL, \n\teffective_from TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\teffective_until TIMESTAMP(3) WITH TIME ZONE, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (activation_id), \n\tCONSTRAINT ck_hf_price_activation_range CHECK (revision>0 AND (effective_until IS NULL OR effective_until>effective_from))\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_activation IS '价格版本生效区间，左闭右开'")
    op.execute("COMMENT ON COLUMN hf_price_activation.activation_id IS '价格生效区间ID'")
    op.execute("COMMENT ON COLUMN hf_price_activation.price_book_id IS '所属价格簿ID'")
    op.execute("COMMENT ON COLUMN hf_price_activation.price_version_id IS '已发布价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_price_activation.effective_from IS '生效起点，含'")
    op.execute("COMMENT ON COLUMN hf_price_activation.effective_until IS '生效终点，不含，空为无穷'")
    op.execute("COMMENT ON COLUMN hf_price_activation.revision IS '区间并发版本'")
    op.execute("COMMENT ON COLUMN hf_price_activation.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_activation.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_activation.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_activation.update_time IS '更新时间'")
    op.execute('CREATE INDEX ix_hf_price_activation_book ON hf_price_activation (price_book_id, effective_from)')
    op.execute(
        "CREATE TABLE hf_price_publish_event (\n\tpublish_event_id BIGSERIAL NOT NULL, \n\tprice_version_id BIGINT NOT NULL, \n\tactivation_id BIGINT NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\taction VARCHAR(32) NOT NULL, \n\treason TEXT NOT NULL, \n\tdiff JSONB NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (publish_event_id), \n\tCONSTRAINT ck_hf_price_publish_event CHECK (action IN ('publish','reschedule','end_activation') AND length(btrim(reason))>0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_price_publish_event IS '只追加价格发布及区间变更历史'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.publish_event_id IS '发布事件ID'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.price_version_id IS '操作价格版本ID'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.activation_id IS '操作生效区间ID'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.actor_id IS '操作用户ID'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.action IS '发布、重新安排或结束区间'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.reason IS '操作依据和原因'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.diff IS '操作前后差异快照'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_price_publish_event.update_time IS '更新时间'")
    op.execute(
        'CREATE INDEX ix_hf_price_publish_event_version ON hf_price_publish_event (price_version_id, create_time)'
    )
    op.execute(
        "INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time) SELECT '发布价格',menu_id,16,'','F','1','0','billing:price:publish','migration_hf_25',CURRENT_TIMESTAMP FROM sys_menu WHERE path='studio-project-permissions' AND NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='billing:price:publish')"
    )


def downgrade():
    op.execute(
        "DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE create_by='migration_hf_25')"
    )
    op.execute("DELETE FROM sys_menu WHERE create_by='migration_hf_25'")
    op.execute('DROP TABLE hf_price_publish_event')
    op.execute('DROP TABLE hf_price_activation')

"""管理成本中心真实建表和管理员测试归属初始化。"""
from alembic import op
revision = '20261028_56'
down_revision = '20261028_55'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_cost_center (
        cost_center_id bigserial PRIMARY KEY, code varchar(100) NOT NULL,
        cost_center_name varchar(200) NOT NULL, active char(1) NOT NULL DEFAULT 'Y',
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT uq_hf_cost_center_code UNIQUE(code),
        CONSTRAINT ck_hf_cost_center_active CHECK(active IN ('Y','N'))
    )""")
    op.execute("COMMENT ON TABLE hf_cost_center IS '管理测试等非项目消费归属'")
    for column, comment in {
        'cost_center_id': '成本中心ID', 'code': '成本中心唯一编码', 'cost_center_name': '成本中心名称',
        'active': '是否允许新消费：Y是N否', 'create_by': '创建者', 'update_by': '更新者',
        'create_time': '创建时间', 'update_time': '更新时间',
    }.items():
        op.execute(f"COMMENT ON COLUMN hf_cost_center.{column} IS '{comment}'")
    op.execute("""INSERT INTO hf_cost_center(code,cost_center_name,create_by,update_by,create_time,update_time)
        VALUES ('admin_test','管理员测试','migration_hf_56','migration_hf_56',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""")


def downgrade():
    raise RuntimeError('成本中心可能已被消费事实引用，不自动删除')

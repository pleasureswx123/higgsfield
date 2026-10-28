"""加入申请持久记录与待审批去重，不开放项目发现。"""
from alembic import op

revision = '20261028_71'
down_revision = '20261028_70'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_project_join_request (
        request_id bigserial PRIMARY KEY,
        project_id bigint NOT NULL, user_id bigint NOT NULL,
        status char(1) NOT NULL DEFAULT '0', reason text,
        reviewer_id bigint, reviewed_time timestamptz(3), revision bigint NOT NULL DEFAULT 1,
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT ck_hf_join_fields CHECK(project_id>0 AND user_id>0 AND revision>0 AND status IN ('0','1','2','3')),
        CONSTRAINT ck_hf_join_reason CHECK(reason IS NULL OR char_length(reason)<=5000),
        CONSTRAINT ck_hf_join_reviewer CHECK((reviewer_id IS NULL AND reviewed_time IS NULL) OR (reviewer_id IS NOT NULL AND reviewer_id>0 AND reviewed_time IS NOT NULL)),
        CONSTRAINT ck_hf_join_review_state CHECK((status='0' AND reviewer_id IS NULL AND reviewed_time IS NULL) OR (status IN ('1','2') AND reviewer_id IS NOT NULL AND reviewed_time IS NOT NULL) OR status='3')
    )""")
    op.execute("CREATE UNIQUE INDEX uq_hf_join_pending ON hf_project_join_request(project_id,user_id) WHERE status='0'")
    op.execute('CREATE INDEX ix_hf_join_project_status_time ON hf_project_join_request(project_id,status,create_time,request_id)')
    op.execute("COMMENT ON TABLE hf_project_join_request IS '项目加入申请及审批状态'")
    for field, label in {
        'request_id': '加入申请ID', 'project_id': '目标项目ID', 'user_id': '申请用户ID',
        'status': '状态：0待审批1批准2拒绝3取消', 'reason': '申请说明', 'reviewer_id': '处理用户ID',
        'reviewed_time': '处理时间', 'revision': '并发修订号', 'create_by': '创建者',
        'update_by': '更新者', 'create_time': '创建时间', 'update_time': '更新时间',
    }.items():
        op.execute(f"COMMENT ON COLUMN hf_project_join_request.{field} IS '{label}'")


def downgrade():
    raise RuntimeError('加入申请保留审批事实，不允许通过自动降级删除历史记录')


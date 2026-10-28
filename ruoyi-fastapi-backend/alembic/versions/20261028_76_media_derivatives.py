"""不可变媒体派生关系与可恢复的缩略图处理租约。"""
from alembic import op

revision = '20261028_76'
down_revision = '20261028_75'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_media_derivative (
        derivative_id bigserial PRIMARY KEY, source_file_id bigint NOT NULL,
        recipe varchar(64) NOT NULL, derived_file_id bigint,
        state char(1) NOT NULL DEFAULT '0', revision bigint NOT NULL DEFAULT 1,
        lease_owner varchar(100), lease_until timestamptz(3),
        attempts integer NOT NULL DEFAULT 0, next_action_time timestamptz(3) NOT NULL,
        error_code varchar(64),
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT uq_hf_derivative_source_recipe UNIQUE(source_file_id,recipe),
        CONSTRAINT uq_hf_derivative_file UNIQUE(derived_file_id),
        CONSTRAINT ck_hf_derivative_state CHECK(state IN ('0','1','2','3','4')),
        CONSTRAINT ck_hf_derivative_identity CHECK(source_file_id>0 AND revision>0 AND attempts>=0
            AND (derived_file_id IS NULL OR (derived_file_id>0 AND derived_file_id<>source_file_id))),
        CONSTRAINT ck_hf_derivative_ready CHECK((state='2')=(derived_file_id IS NOT NULL)),
        CONSTRAINT ck_hf_derivative_lease CHECK(
            (state='1' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR
            (state<>'1' AND lease_owner IS NULL AND lease_until IS NULL)))""")
    op.execute('CREATE INDEX ix_hf_derivative_due ON hf_media_derivative(state,next_action_time,derivative_id)')
    op.execute("COMMENT ON TABLE hf_media_derivative IS '媒体派生文件关系与处理租约，不开放业务删除'")
    comments = {'derivative_id': '派生任务ID', 'source_file_id': '不可变原文件ID', 'recipe': '派生配方版本',
                'derived_file_id': '已登记的派生文件ID', 'state': '0等待1处理中2就绪3待重试4终止失败',
                'revision': '领取及写回并发栅栏', 'lease_owner': '工作器身份', 'lease_until': '领取截止时间',
                'attempts': '累计领取次数', 'next_action_time': '下一次可处理时间', 'error_code': '白名单错误码',
                'create_by': '创建者', 'update_by': '更新者', 'create_time': '创建时间', 'update_time': '更新时间'}
    for name, label in comments.items():
        op.execute(f"COMMENT ON COLUMN hf_media_derivative.{name} IS '{label}'")


def downgrade():
    raise RuntimeError('派生文件已登记时须先制定关系与文件保留方案')

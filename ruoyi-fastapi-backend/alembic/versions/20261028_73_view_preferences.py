"""页面偏好真实存储，按全局和项目范围分别唯一。"""
from alembic import op

revision = '20261028_73'
down_revision = '20261028_72'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_user_view_preference (
        preference_id bigserial PRIMARY KEY, user_id bigint NOT NULL,
        view_key varchar(100) NOT NULL, project_id bigint,
        settings jsonb NOT NULL DEFAULT '{}'::jsonb, revision bigint NOT NULL DEFAULT 1,
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT ck_hf_view_preference_identity CHECK(user_id>0 AND revision>0 AND (project_id IS NULL OR project_id>0)),
        CONSTRAINT ck_hf_view_preference_settings CHECK(view_key IN ('projects','library','elements') AND jsonb_typeof(settings)='object'))""")
    op.execute('CREATE UNIQUE INDEX uq_hf_view_preference_global ON hf_user_view_preference(user_id,view_key) WHERE project_id IS NULL')
    op.execute('CREATE UNIQUE INDEX uq_hf_view_preference_project ON hf_user_view_preference(user_id,view_key,project_id) WHERE project_id IS NOT NULL')
    op.execute("COMMENT ON TABLE hf_user_view_preference IS '本人页面布局与筛选偏好'")
    for field, label in {'preference_id': '偏好ID', 'user_id': '所属用户ID', 'view_key': '页面稳定标识',
                         'project_id': '项目ID，空值表示全局视图', 'settings': '白名单布局与筛选设置',
                         'revision': '并发修订', 'create_by': '创建者', 'update_by': '更新者',
                         'create_time': '创建时间', 'update_time': '更新时间'}.items():
        op.execute(f"COMMENT ON COLUMN hf_user_view_preference.{field} IS '{label}'")


def downgrade():
    raise RuntimeError('页面偏好已有用户数据时须先制定保留方案')

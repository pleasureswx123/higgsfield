"""对账解析失败诊断，不保存原始异常或文件正文。"""
from alembic import op
revision = '20261028_63'
down_revision = '20261028_62'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('ALTER TABLE hf_reconciliation_batch ADD COLUMN import_error jsonb')
    op.execute("COMMENT ON COLUMN hf_reconciliation_batch.import_error IS '文件解析失败白名单诊断，非失败为空'")
    op.execute("ALTER TABLE hf_reconciliation_batch ADD CONSTRAINT ck_hf_reconciliation_import_error "
        "CHECK (import_error IS NULL OR (status='3' AND jsonb_typeof(import_error)='object'))")


def downgrade():
    raise RuntimeError('解析诊断属于账单导入证据，不自动删除')

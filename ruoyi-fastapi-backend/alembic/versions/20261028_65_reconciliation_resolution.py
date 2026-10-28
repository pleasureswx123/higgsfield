"""保留原始账单，独立记录人工采用的观察证据。"""
from alembic import op

revision = '20261028_65'
down_revision = '20261028_64'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""ALTER TABLE hf_reconciliation_line
        ADD COLUMN accepted_observation_id bigint,
        ADD COLUMN accepted_currency varchar(3),
        ADD COLUMN accepted_amount numeric(24,10),
        ADD CONSTRAINT ck_hf_reconciliation_accepted CHECK (
            (accepted_observation_id IS NULL AND accepted_currency IS NULL AND accepted_amount IS NULL)
            OR (accepted_observation_id IS NOT NULL AND accepted_observation_id>0
                AND accepted_currency IS NOT NULL AND accepted_currency ~ '^[A-Z]{3}$'
                AND accepted_amount IS NOT NULL
                AND accepted_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric)))""")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.accepted_observation_id IS '人工解决差异采用的导入观察ID，历史选择保留在审计中'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.accepted_currency IS '所采用观察的币种，不覆盖首次原始币种'")
    op.execute("COMMENT ON COLUMN hf_reconciliation_line.accepted_amount IS '所采用观察的金额，不覆盖首次原始金额'")


def downgrade():
    raise RuntimeError('对账处理证据不可自动删除')

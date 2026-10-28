"""凭据版本在途任务统计的部分索引。"""

from alembic import op

revision = '20261027_30'
down_revision = '20261027_29'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX ix_hf_job_credential_inflight ON hf_creation_job(credential_version_id) WHERE orchestration_state<>'5' OR upstream_state IN ('1','2','6')"
    )


def downgrade():
    op.execute('DROP INDEX ix_hf_job_credential_inflight')

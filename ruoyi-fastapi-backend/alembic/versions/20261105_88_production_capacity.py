"""多人制作受理、恢复参数及队列查询索引。"""
from alembic import op
import sqlalchemy as sa

revision = '20261105_88'
down_revision = '20261103_87'
branch_labels = None
depends_on = None


def upgrade():
    settings = (
        ('userPending', '个人待处理任务上限', '20'),
        ('projectPending', '项目待处理任务上限', '200'),
        ('platformPending', '平台待处理任务上限', '1000'),
        ('videoTrackingSeconds', '视频自动核查窗口秒数', '7200'),
        ('archiveMaxAttempts', '归档自动尝试上限', '5'),
        ('archiveRetryBaseSeconds', '归档首次重试间隔秒数', '60'),
        ('archiveRetryMaxSeconds', '归档最大重试间隔秒数', '1800'),
    )
    for key, name, value in settings:
        op.get_bind().execute(sa.text("""INSERT INTO sys_config
            (config_name,config_key,config_value,config_type,create_by,create_time,remark)
            SELECT :name,CAST(:key AS varchar),:value,'N','migration_88',CURRENT_TIMESTAMP,
                   '多人制作调度参数，必须为1至1000000的整数；修改后新调度生效'
            WHERE NOT EXISTS(SELECT 1 FROM sys_config WHERE config_key=:key)"""),
            {'key': 'hf.production.' + key, 'name': name, 'value': value})
    op.execute("""CREATE INDEX ix_hf_job_pending_scope ON hf_creation_job(actor_id,project_id)
        WHERE orchestration_state IN ('0','1','2','3','4')""")
    op.execute("COMMENT ON INDEX ix_hf_job_pending_scope IS '多人制作三级待处理容量统计索引'")
    op.execute("""CREATE INDEX ix_hf_test_call_capacity ON hf_provider_call(credential_version_id,state)
        WHERE operation='test'""")
    op.execute("COMMENT ON INDEX ix_hf_test_call_capacity IS '管理员测试共享供应商名额查询索引'")


def downgrade():
    op.drop_index('ix_hf_test_call_capacity', table_name='hf_provider_call')
    op.drop_index('ix_hf_job_pending_scope', table_name='hf_creation_job')
    # 保留管理员可能已经调整的参数，不删除业务配置。

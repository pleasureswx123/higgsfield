"""清理初始部门中未修改的演示联系信息，保留真实填写的数据。"""
from alembic import op

revision = '20261109_91'
down_revision = '20261109_90'
branch_labels = None
depends_on = None


def upgrade():
    # 同时匹配初始编号、名称和完整演示联系信息，避免覆盖用户已修改的记录。
    op.execute("""
        UPDATE sys_dept d SET leader=NULL, phone=NULL, email=NULL,
            update_by='migration', update_time=CURRENT_TIMESTAMP
        FROM (VALUES
            (100,'集团总公司'), (101,'深圳分公司'), (102,'长沙分公司'),
            (103,'研发部门'), (104,'市场部门'), (105,'测试部门'),
            (106,'财务部门'), (107,'运维部门'), (108,'市场部门'), (109,'财务部门')
        ) AS seed(dept_id,dept_name)
        WHERE d.dept_id=seed.dept_id AND d.dept_name=seed.dept_name
          AND d.leader='年糕' AND d.phone='15888888888' AND d.email='niangao@qq.com'
    """)


def downgrade():
    # 数据清理不回填虚构联系信息，也不覆盖迁移后填写的真实数据。
    pass

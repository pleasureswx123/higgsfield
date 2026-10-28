"""注册评论作者编辑与治理权限，不自动增加角色授权。"""
from alembic import op
from sqlalchemy import text

revision = '20261028_70'
down_revision = '20261028_69'
branch_labels = None
depends_on = None


def upgrade():
    for permission, label in (('comment:edit:own', '编辑本人评论'), ('comment:moderate', '治理项目评论')):
        op.execute(text("""INSERT INTO sys_menu
            (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
            SELECT :label,menu_id,7,'','F','1','0',:permission,'migration_hf_70',CURRENT_TIMESTAMP
            FROM sys_menu WHERE path='studio-project-permissions'
            AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(label=label, permission=permission))


def downgrade():
    raise RuntimeError('已有评论治理授权需显式处理，不自动删除菜单权限')

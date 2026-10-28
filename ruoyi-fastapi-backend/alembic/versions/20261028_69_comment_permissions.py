"""注册已实现的评论读取与创建按钮权限，不自动扩大既有角色授权。"""
from alembic import op
from sqlalchemy import text

revision = '20261028_69'
down_revision = '20261028_68'
branch_labels = None
depends_on = None


def upgrade():
    for permission, label in (('comment:read', '查看媒体评论'), ('comment:create', '发表媒体评论')):
        op.execute(text("""INSERT INTO sys_menu
            (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
            SELECT :label,menu_id,6,'','F','1','0',:permission,'migration_hf_69',CURRENT_TIMESTAMP
            FROM sys_menu WHERE path='studio-project-permissions'
            AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(label=label, permission=permission))


def downgrade():
    raise RuntimeError('已有评论权限授权需显式治理，不自动删除菜单权限')

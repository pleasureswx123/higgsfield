"""移除后台项目成员入口，保留制作端使用的项目读取授权。"""

from alembic import op
from sqlalchemy import text

revision = '20261029_81'
down_revision = '20261029_80'
branch_labels = None
depends_on = None


def upgrade():
    # 原页面也携带 project:read，将已有角色授权转到独立按钮权限后再删除入口。
    op.execute(text("""
        INSERT INTO sys_role_menu (role_id, menu_id)
        SELECT DISTINCT rm.role_id, target.menu_id
        FROM sys_role_menu rm
        JOIN sys_menu source ON source.menu_id = rm.menu_id
        CROSS JOIN sys_menu target
        WHERE source.component = 'studio/projectMembers/index'
          AND target.menu_type = 'F' AND target.perms = 'project:read'
          AND target.status = '0'
          AND NOT EXISTS (
              SELECT 1 FROM sys_role_menu existing
              WHERE existing.role_id = rm.role_id AND existing.menu_id = target.menu_id
          )
    """))
    op.execute(text("""
        DELETE FROM sys_role_menu
        WHERE menu_id IN (
            SELECT menu_id FROM sys_menu WHERE component = 'studio/projectMembers/index'
        )
    """))
    op.execute(text("DELETE FROM sys_menu WHERE component = 'studio/projectMembers/index'"))


def downgrade():
    raise RuntimeError('后台成员入口已统一到制作平台，恢复入口需单独审核迁移')

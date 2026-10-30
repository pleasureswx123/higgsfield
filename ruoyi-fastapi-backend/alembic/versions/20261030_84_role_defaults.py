"""补齐默认业务角色与制作端系统能力上限，不覆盖项目自定义权限。"""
from alembic import op
import sqlalchemy as sa
revision = '20261030_84'
down_revision = '20261029_83'
branch_labels = None
depends_on = None


def upgrade():
    defaults = {
        'viewer': {code: 'project' for code in 'asset:read element:read comment:read'.split()},
        'producer': {code: 'project' for code in 'asset:read element:read comment:read asset:upload asset:create asset:reference element:create element:import generation:create comment:create comment:edit:own folder:write'.split()},
        'admin': {code: 'project' for code in 'asset:read asset:edit asset:remove element:read element:remove comment:read comment:create comment:edit:own comment:moderate'.split()},
    }
    defaults['producer'].update({code: 'own' for code in 'asset:edit asset:remove element:edit element:remove element:configure content:review'.split()})
    connection = op.get_bind()
    for role, values in defaults.items():
        for code, scope in values.items():
            connection.execute(sa.text("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_by,update_by)
                SELECT role_id,:code,:scope,'migration_84','migration_84' FROM hf_project_role WHERE code=:role
                ON CONFLICT(role_id,permission_code) DO NOTHING"""), {'role': role, 'code': code, 'scope': scope})
    # 系统授权仅提供能力上限，仍须当前项目授权。复用已有按钮菜单，不注册新后台入口。
    op.execute("""INSERT INTO sys_role_menu(role_id,menu_id)
        SELECT r.role_id,m.menu_id FROM sys_role r CROSS JOIN sys_menu m
        WHERE r.role_key='hf_studio_user' AND r.del_flag='0'
        AND m.perms IN ('asset:download','element:copy','project:usage:read') AND m.status='0'
        AND NOT EXISTS(SELECT 1 FROM sys_role_menu rm WHERE rm.role_id=r.role_id AND rm.menu_id=m.menu_id)""")

    # 权限种子变更后使旧身份声明失效，沿用框架认证版本检查。
    op.execute("""DO $$ BEGIN
        IF to_regclass('sys_identity_subject') IS NOT NULL THEN
            UPDATE sys_identity_subject SET auth_version=auth_version+1,
                update_by='migration_84',update_time=CURRENT_TIMESTAMP
            WHERE user_id IN (SELECT ur.user_id FROM sys_user_role ur JOIN sys_role r USING(role_id)
                WHERE r.role_key='hf_studio_user' AND r.del_flag='0');
        END IF;
    END $$""")


def downgrade():
    raise RuntimeError('默认角色授权不可自动删除，请审核后通过授权配置回退')

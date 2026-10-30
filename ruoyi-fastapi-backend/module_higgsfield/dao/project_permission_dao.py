"""项目权限配置查询与写入，事务由服务管理。"""
from sqlalchemy import select
from module_higgsfield.entity.do.project_permission_do import HfProjectPermissionConfig


class ProjectPermissionDao:
    @staticmethod
    async def get(db, project_id):
        return await db.scalar(select(HfProjectPermissionConfig).where(HfProjectPermissionConfig.project_id == project_id))

    @staticmethod
    async def save(db, project_id, row, overrides, audit):
        if row is None:
            row = HfProjectPermissionConfig(project_id=project_id, revision=1, overrides=overrides, **audit)
            db.add(row)
        else:
            row.overrides = overrides
            row.revision += 1
            row.update_by = audit['update_by']
            row.update_time = audit['update_time']
        await db.flush()
        return row

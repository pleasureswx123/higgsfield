from hashlib import sha256

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from module_higgsfield.entity.do.routing_do import HfProjectRoutingSet
from module_higgsfield.entity.do.project_preference_do import HfUserProjectPreference

from module_higgsfield.entity.do.project_do import (
    HfApiIdempotencyRecord,
    HfAssetSpace,
    HfProject,
    HfProjectBrief,
    HfProjectMember,
    HfProjectRole,
    HfProjectRolePermission,
)

STATUS_CODES = {'active': '0', 'paused': '1', 'archived': '2', 'pending_delete': '3'}


class ProjectDao:
    """项目数据库操作，不提交事务。"""

    @staticmethod
    def visible_query(user_id):
        # 成员范围在SQL分页之前施加，管理员通配权限不绕过此条件。
        return (
            select(HfProject, HfProjectRole.code)
            .join(HfProjectMember, HfProjectMember.project_id == HfProject.project_id)
            .join(HfProjectRole, HfProjectRole.role_id == HfProjectMember.role_id)
            .join(
                HfProjectRolePermission,
                (HfProjectRolePermission.role_id == HfProjectRole.role_id)
                & (HfProjectRolePermission.permission_code == 'project:read'),
            )
            .where(HfProject.del_flag == '0', HfProjectMember.user_id == user_id, HfProjectMember.status == '0')
        )

    @classmethod
    async def list_projects(cls, db: AsyncSession, user_id, query):
        preference = HfUserProjectPreference
        statement = cls.visible_query(user_id).outerjoin(preference,
            (preference.project_id == HfProject.project_id) & (preference.user_id == user_id)
        ).add_columns(preference)
        statement = statement.where(func.coalesce(preference.is_hidden, 'N') == ('Y' if query.hidden else 'N'))
        if query.pinned is not None:
            statement = statement.where(func.coalesce(preference.is_pinned, 'N') == ('Y' if query.pinned else 'N'))
        if query.collection_id is not None:
            statement = statement.where(preference.collection_id == int(query.collection_id))
        if query.q.strip():
            statement = statement.where(HfProject.project_name.icontains(query.q.strip(), autoescape=True))
        if query.status:
            statement = statement.where(HfProject.status == STATUS_CODES[query.status])
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        ordering = {
            'created_desc': (HfProject.create_time.desc(), HfProject.project_id.desc()),
            'created_asc': (HfProject.create_time.asc(), HfProject.project_id.asc()),
            'name_asc': (HfProject.project_name.asc(), HfProject.project_id.asc()),
        }
        rows = (
            await db.execute(
                statement.order_by(func.coalesce(preference.is_pinned, 'N').desc(),
                                   func.coalesce(preference.order_num, 0), *ordering[query.sort])
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @classmethod
    async def get_project(cls, db, user_id, project_id):
        return (await db.execute(cls.visible_query(user_id).where(HfProject.project_id == project_id))).first()

    @staticmethod
    async def project_extra(db, project_id):
        space_id = await db.scalar(select(HfAssetSpace.space_id).where(HfAssetSpace.project_id == project_id))
        count = await db.scalar(
            select(func.count())
            .select_from(HfProjectMember)
            .where(HfProjectMember.project_id == project_id, HfProjectMember.status == '0')
        )
        return space_id, count

    @staticmethod
    async def acquire_creation_lock(db, user_id, key):
        # 同一事务内完成本地写入；崩溃即整体回滚，无需持久化外部执行租约。
        lock_id = int.from_bytes(sha256(f'{user_id}:/api/v1:POST:/projects:{key}'.encode()).digest()[:8], signed=True)
        return await db.scalar(select(func.pg_try_advisory_xact_lock(lock_id)))

    @staticmethod
    async def get_idempotency(db, user_id, key):
        return await db.scalar(
            select(HfApiIdempotencyRecord).where(
                HfApiIdempotencyRecord.actor_id == user_id,
                HfApiIdempotencyRecord.api_prefix == '/api/v1',
                HfApiIdempotencyRecord.http_method == 'POST',
                HfApiIdempotencyRecord.normalized_path == '/projects',
                HfApiIdempotencyRecord.idempotency_key == key,
            )
        )

    @staticmethod
    async def create_project(db, name, user_id, username, now):
        # 锁用户行，避免校验与创建之间用户被停用或删除。
        user_exists = await db.scalar(
            text("SELECT user_id FROM sys_user WHERE user_id=:id AND status='0' AND del_flag='0' FOR SHARE").bindparams(
                id=user_id
            )
        )
        if user_exists is None:
            return None
        role_id = await db.scalar(select(HfProjectRole.role_id).where(HfProjectRole.code == 'owner'))
        if role_id is None:
            raise RuntimeError('项目角色未初始化，请执行数据库迁移')
        audit = {'create_by': username, 'update_by': username, 'create_time': now, 'update_time': now}
        project = HfProject(project_name=name, create_user_id=user_id, owner_user_id=user_id, status='0', revision=1, del_flag='0', **audit)
        db.add(project)
        await db.flush()
        db.add_all(
            [
                HfProjectMember(
                    project_id=project.project_id,
                    user_id=user_id,
                    role_id=role_id,
                    status='0',
                    joined_time=now,
                    revision=1,
                    **audit,
                ),
                HfAssetSpace(kind='project', project_id=project.project_id, space_name=name, **audit),
                HfProjectRoutingSet(project_id=project.project_id, revision=1, **audit),
                HfProjectBrief(
                    project_id=project.project_id,
                    body={'schemaVersion': 1, 'type': 'doc', 'content': []},
                    schema_version=1,
                    revision=1,
                    update_user_id=user_id,
                    **audit,
                ),
            ]
        )
        await db.flush()
        return project

    @staticmethod
    async def save_idempotency(db, **values):
        db.add(HfApiIdempotencyRecord(**values))
        await db.flush()

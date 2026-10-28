import json
from datetime import timedelta
from hashlib import sha256

from common.vo import PageModel
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.project_dao import STATUS_CODES, ProjectDao
from module_higgsfield.entity.vo.project_vo import ProjectModel, ProjectPreferenceModel
from utils.response_util import ResponseUtil
from utils.time_util import TimezoneUtil


class ProjectService:
    """项目权限、原子创建与幂等重放。"""

    @staticmethod
    def require_permission(user, permission):
        if permission not in user.permissions and '*:*:*' not in user.permissions:
            raise PermissionException(message='没有执行此项目操作的权限')

    @staticmethod
    def project_model(project, role, **extra):
        return ProjectModel(
            id=str(project.project_id),
            name=project.project_name,
            status={value: key for key, value in STATUS_CODES.items()}[project.status],
            revision=str(project.revision),
            create_time=project.create_time,
            update_time=project.update_time,
            current_user_role=role,
            archived_at=project.archived_time,
            **extra,
        )

    @classmethod
    async def list_projects(cls, db, user, query):
        cls.require_permission(user, 'project:read')
        rows, total = await ProjectDao.list_projects(db, user.user.user_id, query)
        return PageModel[ProjectModel](
            rows=[cls.project_model(project, role, preference=ProjectPreferenceModel(
                project_id=str(project.project_id), is_pinned=bool(pref and pref.is_pinned == 'Y'),
                is_hidden=bool(pref and pref.is_hidden == 'Y'),
                collection_id=str(pref.collection_id) if pref and pref.collection_id else None,
                order_num=pref.order_num if pref else 0, revision=str(pref.revision) if pref else '0',
            )) for project, role, pref in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def get_project(cls, db, user, project_id):
        cls.require_permission(user, 'project:read')
        return await cls.visible_detail(db, user.user.user_id, project_id)

    @classmethod
    async def visible_detail(cls, db, user_id, project_id):
        row = await ProjectDao.get_project(db, user_id, project_id)
        if row is None:
            raise ServiceWarning(message='项目不存在或无权访问', data={'errorCode': 'RESOURCE_NOT_FOUND'})
        space_id, member_count = await ProjectDao.project_extra(db, project_id)
        return cls.project_model(
            row[0], row[1], space_id=str(space_id) if space_id is not None else None, member_count=member_count
        )

    @classmethod
    async def create_project(cls, db, user, payload, key):
        cls.require_permission(user, 'project:create')
        digest = sha256(
            json.dumps(payload.model_dump(), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        user_id, username = user.user.user_id, user.user.user_name
        try:
            if not await ProjectDao.acquire_creation_lock(db, user_id, key):
                raise ServiceWarning(message='项目正在创建，请稍后重试', data={'errorCode': 'IDEMPOTENCY_IN_PROGRESS'})
            existing = await ProjectDao.get_idempotency(db, user_id, key)
            if existing:
                if existing.request_hash != digest:
                    raise ServiceWarning(
                        message='该请求标识已用于其他内容，请重新提交', data={'errorCode': 'IDEMPOTENCY_KEY_REUSED'}
                    )
                if existing.state != '1':
                    raise ServiceWarning(
                        message='请求尚未完成，请稍后重试', data={'errorCode': 'IDEMPOTENCY_IN_PROGRESS'}
                    )
                # 重放仍校验当前成员关系，已撤权用户不能读取原结果。
                await cls.visible_detail(db, user_id, int(existing.result_id))
                result = existing.safe_result
                await db.commit()
                return result, True
            now = TimezoneUtil.utc_now()
            project = await ProjectDao.create_project(db, payload.name, user_id, username, now)
            if project is None:
                raise PermissionException(message='当前用户已停用或删除')
            detail = await cls.visible_detail(db, user_id, project.project_id)
            result = json.loads(ResponseUtil.success(data=detail.model_dump(by_alias=True)).body)
            await ProjectDao.save_idempotency(
                db,
                actor_id=user_id,
                api_prefix='/api/v1',
                http_method='POST',
                normalized_path='/projects',
                idempotency_key=key,
                request_hash=digest,
                state='1',
                http_status=200,
                result_type='project',
                result_id=str(project.project_id),
                safe_result=result,
                expires_time=now + timedelta(days=1),
                completed_time=now,
                fencing_token=1,
                create_by=username,
                update_by=username,
                create_time=now,
                update_time=now,
            )
            await db.commit()
            return result, False
        except Exception:
            await db.rollback()
            raise

"""加入申请审批与成员变更原子提交，读取和重放均实时鉴权。"""
from common.vo import PageModel
from fastapi.encoders import jsonable_encoder
from exceptions.exception import PermissionException
from module_higgsfield.dao.project_join_dao import ProjectJoinDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ProjectJoinService:
    @staticmethod
    def result(row):
        return {'id': str(row.request_id), 'projectId': str(row.project_id), 'userId': str(row.user_id),
            'status': ('pending', 'approved', 'rejected', 'cancelled')[int(row.status)], 'reason': row.reason,
            'reviewerId': str(row.reviewer_id) if row.reviewer_id is not None else None,
            'reviewedTime': row.reviewed_time.isoformat() if row.reviewed_time else None,
            'revision': str(row.revision), 'createTime': row.create_time.isoformat()}

    @classmethod
    async def listing(cls, db, user, project_id, query):
        await WorkspaceService.authorize(db, user, project_id, 'member:manage')
        rows, total = await ProjectJoinDao.page(db, project_id, query)
        return PageModel(rows=[cls.result(row) for row in rows], total=total,
            pageNum=query.page_num, pageSize=query.page_size, hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def review(cls, db, user, identity, payload, key):
        path, prefix = f'/join-requests/{identity}/review', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            row = await ProjectJoinDao.get(db, identity)
            if row is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '申请不存在或无权访问')
            project, actor_role, _ = await WorkspaceService.authorize(db, user, row.project_id, 'member:manage', write=True)
            if actor_role != 'owner':
                raise PermissionException(message='仅项目负责人可以审批加入申请')
            row = await ProjectJoinDao.get(db, identity, lock=True)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(row, payload.revision)
            if row.status != '0':
                WorkspaceService.conflict('JOIN_ALREADY_REVIEWED', '申请已处理，不能重复审批')
            before = cls.result(row)
            member_result = None
            if payload.decision == 'approved':
                member = await WorkspaceService.grant_member(db, user, row.project_id, row.user_id, payload.role_id, actor_role)
                member_result = await WorkspaceService.member_result(db, member)
            audit = WriteService.audit(user)
            row.status = '1' if payload.decision == 'approved' else '2'
            row.reviewer_id, row.reviewed_time = user.user.user_id, audit['update_time']
            row.revision += 1
            row.update_by, row.update_time = audit['update_by'], audit['update_time']
            project.revision += 1
            project.update_by, project.update_time = audit['update_by'], audit['update_time']
            await WorkspaceDao.flush(db)
            after = cls.result(row)
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user', project_id=row.project_id,
                object_type='project_join_request', object_id=str(identity), action=payload.decision,
                reason=payload.reason, request_id=WriteService.digest({'path': path, 'key': key}),
                before_after=jsonable_encoder({'before': before, 'after': after, 'member': member_result}), **audit))
            return await WriteService.finish(db, user, path, key, data, after, 'project_join_request', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise

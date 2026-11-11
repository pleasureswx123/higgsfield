"""制作交接和版本审核；所有写入复用项目锁、权限、并发修订与幂等。"""
from exceptions.exception import PermissionException
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.review_dao import ReviewDao
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.production_workflow import TRANSITIONS, WorkflowError, transition
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil

STATUS_NAMES = dict(zip('01234', ('none', 'working', 'review', 'approved', 'rejected')))
STATUS_CODES = {value: key for key, value in STATUS_NAMES.items()}
REVIEW_ACTIONS = {'approve', 'request_changes'}


class ProductionReviewService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    async def validate_performer(cls, db, project_id, kind, performer_id):
        account = await WorkspaceDao.user(db, performer_id, lock=True)
        member = await ProjectDao.get_project(db, performer_id, project_id)
        if account is None or account['status'] != '0' or account['del_flag'] != '0' or member is None:
            cls.fail('PERFORMER_INVALID', '制作人必须是当前有效项目成员')
        scopes = await WorkspaceDao.permission_scopes(db, member[1], project_id)
        if not scopes.get(f'{kind}:edit'):
            cls.fail('PERFORMER_NOT_ALLOWED', '此成员没有制作权限，请先调整项目角色或选择其他制作人')

    @classmethod
    async def assign(cls, db, user, kind, target_id, payload, key):
        path, data = f'/{kind}s/{target_id}/assignment', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            obj, project = await cls.context(db, user, kind, target_id, write=True)
            # 分配是管理操作，必须具备项目范围编辑权，不能仅凭本人范围转交他人。
            await WorkspaceService.authorize(db, user, project.project_id, f'{kind}:edit', write=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(obj, payload.revision)
            performer_id = int(payload.performer_id) if payload.performer_id else obj.create_user_id
            await cls.validate_performer(db, project.project_id, kind, performer_id)
            obj.performer_id = performer_id
            obj.revision += 1
            obj.update_by, obj.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.flush()
            return await WriteService.finish(db, user, path, key, data,
                                            await cls.get(db, user, kind, target_id), kind, target_id)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def new_version(cls, db, user, obj, kind):
        """新版本重新制作；旧版审核事件保持不变。调用方必须持有项目写锁。"""
        previous = cls.status(obj, kind)
        if previous not in ('review', 'approved', 'rejected'):
            return
        target_id = obj.asset_id if kind == 'asset' else obj.element_id
        await ReviewDao.record(db, kind=kind, target_id=target_id, version_id=cls.version(obj, kind),
                               action='revise', previous=previous, status='working', user=user,
                               reason='内容已更新为新版本，需要重新提交审核')
        cls.set_status(obj, kind, 'working')

    @staticmethod
    def version(obj, kind):
        return obj.current_version_id if kind == 'asset' else obj.current_revision_id

    @staticmethod
    def status(obj, kind):
        return obj.work_status if kind == 'asset' else STATUS_NAMES[obj.work_status]

    @staticmethod
    def set_status(obj, kind, status):
        obj.work_status = status if kind == 'asset' else STATUS_CODES[status]

    @classmethod
    async def context(cls, db, user, kind, target_id, write=False):
        dao = AssetDao if kind == 'asset' else ElementDao
        loader = dao.asset if kind == 'asset' else dao.element
        project_id = await dao.project_id(db, target_id)
        if project_id is None:
            cls.fail('RESOURCE_NOT_FOUND', '内容不存在或无权访问')
        obj = await loader(db, target_id)
        project, _, _ = await WorkspaceService.authorize(
            db, user, project_id, f'{kind}:read', write=write, owner_id=obj.create_user_id)
        # 授权取得项目写锁后重新读取，避免等待锁期间对象被更新。
        if write:
            obj = await loader(db, target_id)
        if obj.del_flag != '0':
            cls.fail('RESOURCE_NOT_FOUND', '内容不存在或已删除')
        return obj, project

    @classmethod
    async def check_ready(cls, db, obj, kind):
        version_id = cls.version(obj, kind)
        if kind == 'asset':
            version = await AssetDao.version(db, version_id)
            file = await AssetDao.file(db, version.file_id) if version else None
            if file is None or file.state != '1':
                cls.fail('FILE_NOT_READY', '媒体文件尚未归档就绪，暂不能提交或通过审核')
        else:
            media = await ElementDao.revision_media(db, version_id)
            if not media:
                cls.fail('ELEMENT_MEDIA_REQUIRED', '请先添加元素参考素材，再提交审核')
            # 固定引用的媒体必须仍可访问，不要求重复通过素材审核。
            for item in media:
                version = await AssetDao.version(db, item.asset_version_id)
                asset = await AssetDao.asset(db, version.asset_id) if version else None
                file = await AssetDao.file(db, version.file_id) if version else None
                if asset is None or asset.del_flag != '0' or file is None or file.state != '1':
                    cls.fail('REFERENCE_UNAVAILABLE', '元素引用的媒体不可用，请更新参考素材后提交')

    @classmethod
    async def act(cls, db, user, kind, target_id, payload, key):
        path = f'/{kind}s/{target_id}/production'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            obj, project = await cls.context(db, user, kind, target_id, write=True)
            review = payload.action in REVIEW_ACTIONS
            await WorkspaceService.authorize(db, user, project.project_id,
                'content:review' if review else f'{kind}:edit', write=True,
                owner_id=None if review else (obj.performer_id or obj.create_user_id))
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(obj, payload.revision)
            version_id, previous = cls.version(obj, kind), cls.status(obj, kind)
            try:
                status = transition(previous, payload.action, current_version_id=version_id,
                                    expected_version_id=int(payload.version_id), reason=payload.reason)
            except WorkflowError as exc:
                cls.fail(exc.code, str(exc))
            if review and not await ReviewDao.submitted(db, kind, target_id, version_id):
                cls.fail('REVIEW_SUBMISSION_REQUIRED', '此版本没有提交审核记录，请先撤回并重新提交')
            if payload.action in ('submit', 'approve'):
                await cls.check_ready(db, obj, kind)
            await ReviewDao.record(db, kind=kind, target_id=target_id, version_id=version_id,
                                   action=payload.action, previous=previous, status=status,
                                   user=user, reason=payload.reason)
            cls.set_status(obj, kind, status)
            obj.revision += 1
            obj.update_by, obj.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.flush()
            return await WriteService.finish(db, user, path, key, data,
                                            await cls.get(db, user, kind, target_id), kind, target_id)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get(cls, db, user, kind, target_id):
        obj, project = await cls.context(db, user, kind, target_id)
        state, version_id = cls.status(obj, kind), cls.version(obj, kind)
        submitted = await ReviewDao.submitted(db, kind, target_id, version_id)
        actions = []
        if project.status == '0':
            for review in (False, True):
                try:
                    await WorkspaceService.authorize(db, user, project.project_id,
                        'content:review' if review else f'{kind}:edit',
                        owner_id=None if review else (obj.performer_id or obj.create_user_id))
                except PermissionException:
                    continue
                actions.extend(action for action, states in TRANSITIONS.items()
                               if state in states and (action in REVIEW_ACTIONS) == review
                               and (not review or submitted))
        approved = await ReviewDao.approved_version(db, kind, target_id)
        history = await ReviewDao.history(db, kind, target_id)
        can_assign = False
        if project.status == '0':
            try:
                await WorkspaceService.authorize(db, user, project.project_id, f'{kind}:edit')
                can_assign = True
            except PermissionException:
                pass
        performer = await WorkspaceDao.user(db, obj.performer_id or obj.create_user_id)
        return {
            'targetId': str(target_id), 'kind': kind, 'revision': str(obj.revision),
            'versionId': str(version_id) if version_id else None, 'workStatus': state,
            'performerId': str(obj.performer_id or obj.create_user_id),
            'performerName': (performer['nick_name'] or performer['user_name']) if performer else '成员不可用',
            'canAssign': can_assign,
            'approvedVersionId': str(approved) if approved else None,
            'reviewVerified': state == 'approved' and approved == version_id,
            'allowedActions': actions,
            'history': [{
                'id': str(row.review_event_id), 'action': row.action,
                'versionId': str(row.asset_version_id or row.element_revision_id)
                    if row.asset_version_id or row.element_revision_id else None,
                'actorId': str(row.actor_id), 'actorName': row.create_by,
                'fromStatus': row.from_status, 'toStatus': row.to_status,
                'reason': row.reason or '', 'createTime': row.create_time,
            } for row in history],
        }

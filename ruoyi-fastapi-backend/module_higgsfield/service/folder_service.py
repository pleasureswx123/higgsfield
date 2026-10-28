import json
from datetime import timedelta
from hashlib import sha256

from common.vo import PageModel
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.folder_do import HfFolder, HfRecycleEntry
from module_higgsfield.entity.vo.folder_vo import FolderCreate, normalized_name
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.folder_content_service import FolderContentService
from utils.response_util import ResponseUtil
from utils.time_util import TimezoneUtil


class FolderService:
    """项目授权、目录层级、修订及幂等在同一事务中校验。"""

    fail = WorkspaceService.conflict

    @staticmethod
    def result(folder, project_id, has_children=False):
        return {
            'id': str(folder.folder_id),
            'projectId': str(project_id),
            'parentId': str(folder.parent_id) if folder.parent_id else None,
            'name': folder.folder_name,
            'description': folder.description,
            'color': folder.color,
            'folderKind': folder.folder_kind,
            'orderNum': folder.order_num,
            'revision': str(folder.revision),
            'hasChildren': has_children,
        }

    @classmethod
    async def list(cls, db, user, project_id, query):
        await WorkspaceService.authorize(db, user, project_id, 'asset:read')
        space = await FolderDao.space(db, project_id)
        rows, total = await FolderDao.list(db, space.space_id, query)
        return PageModel(
            rows=[cls.result(row, project_id, children) for row, children in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def detail(cls, db, user, folder_id):
        project_id = await FolderDao.project_id(db, folder_id)
        if project_id is None:
            cls.fail('RESOURCE_NOT_FOUND', '目录不存在或无权访问')
        await WorkspaceService.authorize(db, user, project_id, 'asset:read')
        space = await FolderDao.space(db, project_id)
        path, seen = [], set()
        current = folder_id
        while current is not None:
            if current in seen:
                cls.fail('FOLDER_CYCLE', '目录层级异常，请联系管理员')
            seen.add(current)
            folder = await FolderDao.get(db, current)
            if folder is None or folder.space_id != space.space_id or folder.del_flag != '0':
                cls.fail('RESOURCE_NOT_FOUND', '目录不存在或已删除')
            path.append(cls.result(folder, project_id))
            current = folder.parent_id
        return {'folder': path[0], 'ancestors': list(reversed(path[1:]))}

    @classmethod
    async def trash(cls, db, user, project_id, page_num, page_size):
        await WorkspaceService.authorize(db, user, project_id, 'folder:write')
        rows, total = await FolderDao.trash(db, project_id, page_num, page_size)
        now = TimezoneUtil.utc_now()
        result = []
        for row in rows:
            folder = await FolderDao.get(db, row.target_id)
            result.append(
                {
                    'id': str(row.recycle_id),
                    'targetId': str(row.target_id),
                    'kind': 'folder',
                    'name': row.snapshot['name'],
                    'revision': str(folder.revision),
                    'deletedTime': row.deleted_time,
                    'restoreUntil': row.restore_until,
                    'canRestore': row.restore_until > now,
                }
            )
        return PageModel(
            rows=result, pageNum=page_num, pageSize=page_size, total=total, hasNext=page_num * page_size < total
        )

    @classmethod
    async def check_target(cls, db, space_id, parent_id, kind, source_id=None):
        seen = set()
        current = parent_id
        while current is not None:
            if current == source_id or current in seen:
                cls.fail('FOLDER_CYCLE', '不能移动或复制到自身及其子目录')
            seen.add(current)
            parent = await FolderDao.get(db, current)
            if parent is None or parent.space_id != space_id or parent.del_flag != '0' or parent.folder_kind != kind:
                cls.fail('INVALID_PARENT', '目标目录不存在、已删除或类型不同')
            current = parent.parent_id

    @classmethod
    async def check_name(cls, db, space_id, parent_id, name, exclude=None):
        normalized = normalized_name(name)
        if any(
            item.normalized_name == normalized and item.folder_id != exclude
            for item in await FolderDao.siblings(db, space_id, parent_id)
        ):
            cls.fail('FOLDER_NAME_EXISTS', '目标位置已有同名目录，请修改名称或目标位置')

    @classmethod
    async def mutate(cls, db, user, action, payload, key, project_id=None, folder_id=None):
        methods = {
            'create': 'POST',
            'edit': 'PATCH',
            'move': 'POST',
            'copy': 'POST',
            'delete': 'DELETE',
            'restore': 'POST',
        }
        path = f'/projects/{project_id}/folders' if action == 'create' else f'/folders/{folder_id}'
        if action in ('move', 'copy', 'restore'):
            path += '/' + action
        digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        try:
            if project_id is None:
                project_id = await FolderDao.project_id(db, folder_id)
            if project_id is None:
                cls.fail('RESOURCE_NOT_FOUND', '目录不存在或无权访问')
            await WorkspaceService.authorize(db, user, project_id, 'folder:write', write=True)
            space = await FolderDao.space(db, project_id, lock=True)
            replay = await WorkspaceDao.replay(db, user.user.user_id, methods[action], path, key) if key else None
            if replay:
                if replay.request_hash != digest:
                    cls.fail('IDEMPOTENCY_KEY_REUSED', '请求标识已用于不同内容')
                if replay.state != '1':
                    cls.fail('IDEMPOTENCY_IN_PROGRESS', '请求尚未完成')
                await db.commit()
                return replay.safe_result, True
            now = TimezoneUtil.utc_now()
            audit = {
                'create_by': user.user.user_name,
                'update_by': user.user.user_name,
                'create_time': now,
                'update_time': now,
            }
            folder = None
            if action != 'create':
                folder = await FolderDao.get(db, folder_id)
                if (
                    folder is None
                    or folder.space_id != space.space_id
                    or folder.del_flag != ('2' if action == 'restore' else '0')
                ):
                    cls.fail('RESOURCE_NOT_FOUND', '目录不存在或状态已变化')
                WorkspaceService.check_revision(folder, payload['revision'])
            if action == 'create':
                parent = int(payload['parentId']) if payload.get('parentId') else None
                await cls.check_target(db, space.space_id, parent, payload['folderKind'])
                await cls.check_name(db, space.space_id, parent, payload['name'])
                folder = await FolderDao.add(
                    db,
                    HfFolder,
                    space_id=space.space_id,
                    parent_id=parent,
                    folder_name=payload['name'],
                    normalized_name=normalized_name(payload['name']),
                    description=payload['description'],
                    color=payload['color'],
                    folder_kind=payload['folderKind'],
                    order_num=0,
                    revision=1,
                    del_flag='0',
                    **audit,
                )
            elif action == 'edit':
                if payload.get('name') is not None:
                    await cls.check_name(db, space.space_id, folder.parent_id, payload['name'], folder_id)
                    folder.folder_name, folder.normalized_name = payload['name'], normalized_name(payload['name'])
                for field, attribute in [('description', 'description'), ('color', 'color'), ('orderNum', 'order_num')]:
                    if payload.get(field) is not None:
                        setattr(folder, attribute, payload[field])
            elif action in ('move', 'restore'):
                recycle = await FolderDao.recycle(db, folder_id) if action == 'restore' else None
                if action == 'restore' and (recycle is None or recycle.restore_until <= now):
                    cls.fail('RESTORE_EXPIRED', '自助恢复期限已过或回收记录不存在')
                value = (
                    payload.get('parentId')
                    if action == 'move'
                    else payload.get('targetParentId', recycle.original_parent_id)
                )
                parent = int(value) if value else None
                await cls.check_target(db, space.space_id, parent, folder.folder_kind, folder_id)
                await cls.check_name(db, space.space_id, parent, folder.folder_name, folder_id)
                folder.parent_id, folder.del_flag = parent, '0'
                if recycle:
                    recycle.state, recycle.restored_time, recycle.restored_by = 'restored', now, user.user.user_id
                    recycle.revision += 1
                    recycle.update_by, recycle.update_time = user.user.user_name, now
            elif action == 'delete':
                children = await FolderDao.siblings(db, space.space_id, folder_id)
                # 将子目录移至父级；冲突时整个删除回滚，绝不递归删除内容。
                for child in children:
                    await cls.check_name(db, space.space_id, folder.parent_id, child.folder_name, folder_id)
                # 先释放活跃名称，避免父子同名时受ORM更新顺序影响。
                folder.del_flag = '2'
                await FolderDao.flush(db)
                await FolderContentService.move_to_parent(
                    db, user, space.space_id, folder_id, folder.parent_id, folder.folder_kind
                )
                for child in children:
                    child.parent_id = folder.parent_id
                    child.revision += 1
                    child.update_by, child.update_time = user.user.user_name, now
                folder.del_flag = '2'
                await FolderDao.add(
                    db,
                    HfRecycleEntry,
                    project_id=project_id,
                    target_kind='folder',
                    target_id=folder_id,
                    original_parent_id=folder.parent_id,
                    deleted_time=now,
                    restore_until=now + timedelta(days=30),
                    actor_id=user.user.user_id,
                    state='active',
                    revision=1,
                    snapshot={'name': folder.folder_name, 'folderKind': folder.folder_kind},
                    **audit,
                )
            elif action == 'copy':
                parent = int(payload['targetParentId']) if payload.get('targetParentId') else None
                try:
                    name = FolderCreate.valid_name(payload.get('name') or 'Copy of ' + folder.folder_name)
                except ValueError:
                    cls.fail('INVALID_FOLDER_NAME', '复制名称超过长度限制，请指定较短名称')
                await cls.check_target(db, space.space_id, parent, folder.folder_kind, folder_id)
                await cls.check_name(db, space.space_id, parent, name)
                queue = [(folder, parent, name)]
                root = None
                for source, target, target_name in queue:
                    children = await FolderDao.siblings(db, space.space_id, source.folder_id)
                    copied = await FolderDao.add(
                        db,
                        HfFolder,
                        space_id=space.space_id,
                        parent_id=target,
                        folder_name=target_name,
                        normalized_name=normalized_name(target_name),
                        description=source.description,
                        color=source.color,
                        folder_kind=source.folder_kind,
                        order_num=source.order_num,
                        revision=1,
                        del_flag='0',
                        **audit,
                    )
                    root = root or copied
                    await FolderContentService.copy(
                        db, user, project_id, space.space_id, source.folder_id, copied.folder_id, source.folder_kind
                    )
                    queue.extend((child, copied.folder_id, child.folder_name) for child in children)
                folder = root
            if action not in ('create', 'copy'):
                folder.revision += 1
                folder.update_by, folder.update_time = user.user.user_name, now
            await FolderDao.flush(db)
            result = cls.result(
                folder, project_id, bool(await FolderDao.siblings(db, space.space_id, folder.folder_id))
            )
            response = json.loads(ResponseUtil.success(data=result).body)
            if key:
                await ProjectDao.save_idempotency(
                    db,
                    actor_id=user.user.user_id,
                    api_prefix='/api/v1',
                    http_method=methods[action],
                    normalized_path=path,
                    idempotency_key=key,
                    request_hash=digest,
                    state='1',
                    http_status=200,
                    result_type='folder',
                    result_id=str(folder.folder_id),
                    safe_result=response,
                    expires_time=now + timedelta(days=1),
                    completed_time=now,
                    fencing_token=1,
                    **audit,
                )
            await db.commit()
            return response, False
        except Exception:
            await db.rollback()
            raise

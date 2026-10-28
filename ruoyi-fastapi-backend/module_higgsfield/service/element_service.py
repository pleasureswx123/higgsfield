"""元素身份、不可变内容及标签在同一授权事务中保存。"""

from datetime import timedelta
from math import ceil

from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.element_do import HfElement, HfPropertyDefinition
from module_higgsfield.entity.do.review_do import HfReviewEvent
from module_higgsfield.entity.do.folder_do import HfRecycleEntry
from module_higgsfield.service.element_content_service import ElementContentService
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil

STATUS_CODES = dict(zip(('none', 'working', 'review', 'approved', 'rejected'), '01234'))
STATUS_NAMES = {value: key for key, value in STATUS_CODES.items()}


class ElementService:
    fail = staticmethod(WorkspaceService.conflict)

    @staticmethod
    def result(element, project_id=None):
        return {
            'id': str(element.element_id),
            'spaceId': str(element.space_id),
            'projectId': str(project_id) if project_id else None,
            'name': element.element_name,
            'alias': element.alias,
            'category': element.category,
            'currentRevisionId': str(element.current_revision_id) if element.current_revision_id else None,
            'performerId': str(element.performer_id) if element.performer_id else None,
            'folderId': str(element.folder_id) if element.folder_id else None,
            'workStatus': STATUS_NAMES[element.work_status],
            'revision': str(element.revision),
            'createUserId': str(element.create_user_id),
            'createTime': element.create_time,
        }

    @classmethod
    async def authorized(cls, db, user, element_id, permission, write=False, include_deleted=False):
        project_id = await ElementDao.project_id(db, element_id)
        if project_id is None:
            cls.fail('RESOURCE_NOT_FOUND', '元素不存在或无权访问')
        element = await ElementDao.element(db, element_id)
        project, _, allowed = await WorkspaceService.authorize(
            db, user, project_id, permission, write=write, owner_id=element.create_user_id
        )
        if write:
            element = await ElementDao.element(db, element_id)
        if element.del_flag != '0' and not include_deleted:
            cls.fail('RESOURCE_NOT_FOUND', '元素不存在或已删除')
        return element, project, allowed

    @classmethod
    async def lifecycle(cls, db, user, element_id, action, payload, key=None):
        path = f'/elements/{element_id}' + ('/restore' if action == 'restore' else '')
        method = 'POST' if action == 'restore' else 'DELETE'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            element, project, _ = await cls.authorized(
                db, user, element_id, 'element:remove', write=True, include_deleted=True
            )
            replay = await WriteService.replay(db, user, path, key, data, method)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(element, payload.revision)
            await FolderDao.space(db, project.project_id, lock=True)
            now = TimezoneUtil.utc_now()
            if action == 'delete':
                if element.del_flag != '0':
                    cls.fail('RESOURCE_REMOVED', '元素已在回收站中')
                await ElementDao.add(
                    db,
                    HfRecycleEntry,
                    project_id=project.project_id,
                    target_kind='element',
                    target_id=element_id,
                    original_parent_id=element.folder_id,
                    deleted_time=now,
                    restore_until=now + timedelta(days=30),
                    actor_id=user.user.user_id,
                    state='active',
                    revision=1,
                    snapshot={
                        'name': element.element_name,
                        'alias': element.alias,
                        'category': element.category,
                        'currentRevisionId': str(element.current_revision_id),
                    },
                    **WriteService.audit(user),
                )
                element.del_flag = '2'
            else:
                recycle = await ElementDao.recycle(db, element_id)
                if element.del_flag != '2' or recycle is None:
                    cls.fail('RESOURCE_NOT_REMOVED', '元素不在回收站中')
                if recycle.restore_until <= now:
                    cls.fail('RESTORE_EXPIRED', '自助恢复期限已过，请联系项目管理员')
                parent_id = recycle.original_parent_id
                if parent_id is not None:
                    parent = await FolderDao.get(db, parent_id)
                    if (
                        parent is None
                        or parent.del_flag != '0'
                        or parent.space_id != element.space_id
                        or parent.folder_kind != 'element'
                    ):
                        cls.fail('RESTORE_PARENT_UNAVAILABLE', '原元素目录不可用，请先恢复目录')
                await FolderService.check_target(db, element.space_id, parent_id, 'element')
                element.del_flag, element.folder_id = '0', parent_id
                recycle.state, recycle.restored_time, recycle.restored_by = 'restored', now, user.user.user_id
                recycle.revision += 1
                recycle.update_by, recycle.update_time = user.user.user_name, now
            element.revision += 1
            element.update_by, element.update_time = user.user.user_name, now
            await db.flush()
            return await WriteService.finish(
                db, user, path, key, data, cls.result(element, project.project_id), 'element', element_id, method
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def trash(cls, db, user, project_id, page_num, page_size):
        project, role, _ = await WorkspaceService.authorize(db, user, project_id, 'project:read')
        scopes = await WorkspaceDao.permission_scopes(db, role)
        scope = scopes.get('element:remove')
        if scope is None or ('*:*:*' not in user.permissions and 'element:remove' not in user.permissions):
            raise PermissionException(message='没有查看元素回收站的权限')
        rows, total = await ElementDao.trash(
            db, project_id, user.user.user_id if scope == 'own' else None, page_num, page_size
        )
        now, items = TimezoneUtil.utc_now(), []
        for entry, element in rows:
            remaining = max(0, ceil((entry.restore_until - now).total_seconds() / 86400))
            can_restore = remaining > 0 and project.status == '0'
            items.append(
                {
                    'id': str(entry.recycle_id),
                    'projectId': str(project_id),
                    'targetKind': 'element',
                    'targetId': str(element.element_id),
                    'name': element.element_name,
                    'originalParentId': str(entry.original_parent_id) if entry.original_parent_id else None,
                    'deletedTime': entry.deleted_time,
                    'restoreUntil': entry.restore_until,
                    'remainingDays': remaining,
                    'revision': str(element.revision),
                    'canRestore': can_restore,
                    'allowedActions': ['element:restore'] if can_restore else [],
                }
            )
        return PageModel(
            rows=items, pageNum=page_num, pageSize=page_size, total=total, hasNext=page_num * page_size < total
        )

    @classmethod
    async def detail(cls, db, user, element_id):
        element, project, allowed = await cls.authorized(db, user, element_id, 'element:read')
        if project.status != '0':
            allowed = allowed - {'element:edit', 'element:remove', 'element:configure', 'content:review'}
        result = cls.result(element, project.project_id)
        result['allowedActions'] = sorted(allowed)
        return {
            'element': result,
            'currentRevision': await ElementContentService.result(
                db, await ElementDao.revision(db, element.current_revision_id)
            ),
        }

    @classmethod
    async def listing(cls, db, user, query):
        if '*:*:*' not in user.permissions and 'element:read' not in user.permissions:
            raise PermissionException(message='没有查看元素的系统权限')
        if query.project_id:
            # 列表的本人范围在SQL中按每个对象作者校验，不能用空作者误拒绝 own 读取。
            await WorkspaceService.authorize(db, user, int(query.project_id), 'project:read')
            if query.folder_id:
                space = await FolderDao.space(db, int(query.project_id))
                await FolderService.check_target(db, space.space_id, int(query.folder_id), 'element')
        rows, total = await ElementDao.list_elements(db, user.user.user_id, query, STATUS_CODES)
        return PageModel(
            rows=[{**cls.result(row, project_id), 'projectName': project_name, 'description': description,
                   'label': label or '', 'revisionNo': revision_no}
                  for row, project_id, project_name, description, label, revision_no in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def validate_fields(cls, db, user, project_id, payload, element=None):
        if payload.performer_id:
            member = await WorkspaceDao.member(db, project_id, int(payload.performer_id))
            target = await WorkspaceDao.user(db, int(payload.performer_id), lock=True)
            if (
                member is None
                or member.status != '0'
                or target is None
                or target['status'] != '0'
                or target['del_flag'] != '0'
            ):
                cls.fail('PERFORMER_INVALID', '负责人必须是当前有效项目成员')
        previous = STATUS_NAMES[element.work_status] if element else 'none'
        if previous != payload.work_status:
            await WorkspaceService.authorize(
                db,
                user,
                project_id,
                'content:review',
                write=True,
                owner_id=element.create_user_id if element else user.user.user_id,
            )

    @staticmethod
    async def set_status(db, user, element, status):
        previous = STATUS_NAMES[element.work_status]
        if previous != status:
            await ElementDao.add(
                db,
                HfReviewEvent,
                element_id=element.element_id,
                actor_id=user.user.user_id,
                from_status=previous,
                to_status=status,
                **WriteService.audit(user),
            )
            element.work_status = STATUS_CODES[status]

    @classmethod
    async def create_in_transaction(cls, db, user, payload):
        """调用方须先授权并持有项目写锁；本方法不提交事务。"""
        project_id = int(payload.project_id)
        space = await FolderDao.space(db, project_id, lock=True)
        if await ElementDao.alias_exists(db, space.space_id, payload.alias):
            cls.fail('ALIAS_CONFLICT', '此项目已使用该别名，回收元素的别名也会保留')
        await FolderService.check_target(
            db, space.space_id, int(payload.folder_id) if payload.folder_id else None, 'element'
        )
        await cls.validate_fields(db, user, project_id, payload)
        snapshots = await ElementContentService.validate(db, user, project_id, space.space_id, payload)
        element = await ElementDao.add(
            db,
            HfElement,
            space_id=space.space_id,
            element_name=payload.name,
            alias=payload.alias,
            category=payload.category,
            create_user_id=user.user.user_id,
            performer_id=int(payload.performer_id) if payload.performer_id else None,
            folder_id=int(payload.folder_id) if payload.folder_id else None,
            **WriteService.audit(user),
        )
        revision = await ElementContentService.append(db, user, element, payload, snapshots, payload.label)
        await cls.set_status(db, user, element, payload.work_status)
        result = {
            'element': cls.result(element, project_id),
            'currentRevision': await ElementContentService.result(db, revision),
        }
        return result

    @classmethod
    async def create(cls, db, user, payload, key):
        path, data, project_id = '/elements', payload.model_dump(by_alias=True), int(payload.project_id)
        try:
            await WriteService.lock(db, user, path, key)
            await WorkspaceService.authorize(
                db, user, project_id, 'element:create', write=True, owner_id=user.user.user_id
            )
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            result = await cls.create_in_transaction(db, user, payload)
            return await WriteService.finish(db, user, path, key, data, result, 'element', int(result['element']['id']))
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def mutate(cls, db, user, element_id, action, payload, key=None):
        path = f'/elements/{element_id}' + ('' if action == 'patch' else '/' + action)
        method, data = (
            ('PATCH' if action == 'patch' else 'POST'),
            payload.model_dump(by_alias=True, exclude_unset=action == 'patch'),
        )
        try:
            await WriteService.lock(db, user, path, key)
            element, project, _ = await cls.authorized(db, user, element_id, 'element:edit', write=True)
            replay = await WriteService.replay(db, user, path, key, data, method)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(element, payload.revision)
            if action in ('patch', 'save'):
                if 'alias' in data and await ElementDao.alias_exists(db, element.space_id, payload.alias, element_id):
                    cls.fail('ALIAS_CONFLICT', '此项目已使用该别名')
                for field, column in (('name', 'element_name'), ('alias', 'alias'), ('category', 'category')):
                    if field in data:
                        setattr(element, column, getattr(payload, field))
            revision = await ElementDao.revision(db, element.current_revision_id)
            if action in ('save', 'revisions'):
                if action == 'save':
                    await cls.validate_fields(db, user, project.project_id, payload, element)
                    element.performer_id = int(payload.performer_id) if payload.performer_id else None
                    await cls.set_status(db, user, element, payload.work_status)
                snapshots = await ElementContentService.validate(
                    db, user, project.project_id, element.space_id, payload
                )
                previous = await ElementContentService.result(db, revision)
                media = sorted(
                    [item.model_dump(by_alias=True) for item in payload.media], key=lambda item: item['ordinal']
                )
                changed = (
                    revision.description != payload.description
                    or revision.property_snapshot != snapshots
                    or previous['media'] != media
                )
                if changed:
                    revision = await ElementContentService.append(
                        db, user, element, payload, snapshots, payload.label if action == 'save' else ''
                    )
                elif action == 'save':
                    label = await ElementDao.label(db, revision.revision_id)
                    if label.label != payload.label:
                        label.label, label.revision = payload.label, label.revision + 1
                        label.update_user_id, label.update_by, label.update_time = (
                            user.user.user_id,
                            user.user.user_name,
                            TimezoneUtil.utc_now(),
                        )
            elif action == 'move':
                folder_id = int(payload.folder_id) if payload.folder_id else None
                await FolderService.check_target(db, element.space_id, folder_id, 'element')
                element.folder_id = folder_id
            element.revision += 1
            element.update_by, element.update_time = user.user.user_name, TimezoneUtil.utc_now()
            await db.flush()
            result = cls.result(element, project.project_id)
            if action == 'save':
                result = {'element': result, 'currentRevision': await ElementContentService.result(db, revision)}
            elif action == 'revisions':
                result = await ElementContentService.result(db, revision)
            return await WriteService.finish(db, user, path, key, data, result, 'element', element_id, method)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def revisions(cls, db, user, element_id, page_num, page_size):
        await cls.authorized(db, user, element_id, 'element:read')
        rows, total = await ElementDao.revisions(db, element_id, page_num, page_size)
        return PageModel(
            rows=[await ElementContentService.result(db, row) for row in rows],
            pageNum=page_num,
            pageSize=page_size,
            total=total,
            hasNext=page_num * page_size < total,
        )

    @classmethod
    async def label(cls, db, user, revision_id, payload, key=None):
        path, data = f'/element-revisions/{revision_id}/label', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            revision = await ElementDao.revision(db, revision_id)
            if revision is None:
                cls.fail('RESOURCE_NOT_FOUND', '修订不存在或无权访问')
            element, _, _ = await cls.authorized(db, user, revision.element_id, 'element:edit', write=True)
            replay = await WriteService.replay(db, user, path, key, data, 'PATCH')
            if replay:
                await db.commit()
                return replay, True
            label = await ElementDao.label(db, revision_id)
            WorkspaceService.check_revision(label, payload.revision)
            label.label, label.revision = payload.label, label.revision + 1
            label.update_user_id = user.user.user_id
            label.update_by, label.update_time = user.user.user_name, TimezoneUtil.utc_now()
            # 标签独立版本用于精确编辑；身份版本同时推进，防旧详情整表单覆盖新标签。
            element.revision += 1
            element.update_by, element.update_time = label.update_by, label.update_time
            await db.flush()
            result = {'elementRevisionId': str(revision_id), 'label': label.label, 'revision': str(label.revision)}
            return await WriteService.finish(
                db, user, path, key, data, result, 'element_revision_label', label.label_id, 'PATCH'
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def property_result(row):
        return {
            'id': str(row.property_id),
            'propertyKey': row.property_key,
            'versionNo': row.version_no,
            'name': row.property_name,
            'valueType': row.value_type,
            'options': row.options,
        }

    @classmethod
    async def definitions(cls, db, user, project_id, page_num, page_size):
        await WorkspaceService.authorize(db, user, project_id, 'element:read')
        space = await FolderDao.space(db, project_id)
        rows, total = await ElementDao.definitions(db, space.space_id, page_num, page_size)
        return PageModel(
            rows=[cls.property_result(row) for row in rows],
            pageNum=page_num,
            pageSize=page_size,
            total=total,
            hasNext=page_num * page_size < total,
        )

    @classmethod
    async def write_definition(cls, db, user, payload, key, project_id=None, definition_id=None):
        path = (
            f'/property-definitions/{definition_id}/versions'
            if definition_id
            else f'/projects/{project_id}/property-definitions'
        )
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            previous = await ElementDao.definition(db, definition_id) if definition_id else None
            if definition_id:
                if previous is None:
                    cls.fail('RESOURCE_NOT_FOUND', '属性定义不存在或无权访问')
                project_id = await ElementDao.space_project(db, previous.space_id)
            await WorkspaceService.authorize(db, user, project_id, 'element:configure', write=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            space = await FolderDao.space(db, project_id, lock=True)
            property_key = previous.property_key if previous else payload.property_key
            latest = await ElementDao.latest_definition(db, space.space_id, property_key)
            if latest and not previous:
                cls.fail('PROPERTY_KEY_CONFLICT', '属性键已存在，请创建定义的新版本')
            if previous and latest.property_id != previous.property_id:
                cls.fail('VERSION_CONFLICT', '属性定义已有新版本，请重新加载')
            row = await ElementDao.add(
                db,
                HfPropertyDefinition,
                space_id=space.space_id,
                property_key=property_key,
                version_no=latest.version_no + 1 if latest else 1,
                property_name=payload.name,
                value_type=payload.value_type,
                options=payload.options,
                **WriteService.audit(user),
            )
            return await WriteService.finish(
                db, user, path, key, data, cls.property_result(row), 'property_definition', row.property_id
            )
        except Exception:
            await db.rollback()
            raise

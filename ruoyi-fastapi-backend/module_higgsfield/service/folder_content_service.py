from uuid import uuid4

from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.entity.do.element_do import HfElement
from module_higgsfield.entity.vo.element_vo import RevisionContent
from module_higgsfield.service.element_content_service import ElementContentService
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class FolderContentService:
    """目录内容复制产生新身份并固定来源版本，不复制NAS字节。"""

    @staticmethod
    async def move_to_parent(db, user, space_id, folder_id, parent_id, kind='media'):
        audit = WriteService.audit(user)
        if kind == 'element':
            for element in await ElementDao.in_folder(db, space_id, folder_id):
                element.folder_id = parent_id
                element.revision += 1
                element.update_by, element.update_time = audit['update_by'], audit['update_time']
            return
        for entry in await AssetDao.entries(db, space_id, folder_id):
            entry.folder_id = parent_id
            entry.revision += 1
            entry.update_by, entry.update_time = audit['update_by'], audit['update_time']

    @staticmethod
    async def copy(db, user, project_id, space_id, source_id, target_id, kind='media', entry_id=None):
        if kind == 'element':
            for source in await ElementDao.in_folder(db, space_id, source_id):
                for permission in ('element:read', 'element:copy'):
                    await WorkspaceService.authorize(db, user, project_id, permission, owner_id=source.create_user_id)
                await WorkspaceService.authorize(
                    db, user, project_id, 'element:create', write=True, owner_id=user.user.user_id
                )
                revision = await ElementDao.revision(db, source.current_revision_id)
                result = await ElementContentService.result(db, revision)
                content = RevisionContent(
                    description=result['description'], propertyValues=result['propertyValues'], media=result['media']
                )
                snapshots = await ElementContentService.validate(db, user, project_id, space_id, content)
                for _, asset, _ in await ElementDao.media_sources(
                    db, [int(item.asset_version_id) for item in content.media]
                ):
                    await WorkspaceService.authorize(
                        db, user, project_id, 'asset:reference', owner_id=asset.create_user_id
                    )
                copied = await ElementDao.add(
                    db,
                    HfElement,
                    space_id=space_id,
                    element_name=source.element_name,
                    alias=source.alias[:65] + '-copy-' + uuid4().hex[:28],
                    category=source.category,
                    create_user_id=user.user.user_id,
                    folder_id=target_id,
                    **WriteService.audit(user),
                )
                await ElementContentService.append(db, user, copied, content, snapshots, result['label'])
            return
        entries = ([await AssetDao.entry(db, space_id, entry_id)] if entry_id is not None
                   else await AssetDao.entries(db, space_id, source_id))
        if entries:
            await WorkspaceService.authorize(
                db, user, project_id, 'asset:create', write=True, owner_id=user.user.user_id
            )
        audit = WriteService.audit(user)
        for entry in entries:
            if entry.asset_id is None:
                WorkspaceService.conflict('FOLDER_CONTENT_NOT_READY', '目录含尚未可复制的作品或跨项目引用')
            source = await AssetDao.asset(db, entry.asset_id)
            if source is None or source.space_id != space_id:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '目录内容归属异常')
            if source.del_flag != '0':
                continue
            for permission in ('asset:read', 'asset:reference'):
                await WorkspaceService.authorize(db, user, project_id, permission, owner_id=source.create_user_id)
            version = await AssetDao.version(db, source.current_version_id)
            file = await AssetDao.file(db, version.file_id)
            if file.state != '1':
                WorkspaceService.conflict('FILE_NOT_READY', '目录内容尚未归档，不能复制')
            copied = await AssetDao.add(
                db,
                HfAsset,
                space_id=space_id,
                asset_name=source.asset_name,
                media_type=source.media_type,
                create_user_id=user.user.user_id,
                revision=1,
                del_flag='0',
                **audit,
            )
            copied_version = await AssetDao.add(
                db,
                HfAssetVersion,
                asset_id=copied.asset_id,
                version_no=1,
                file_id=file.file_id,
                create_user_id=user.user.user_id,
                media_metadata=version.media_metadata,
                source_asset_version_id=version.version_id,
                **audit,
            )
            copied.current_version_id = copied_version.version_id
            copied_entry = await AssetDao.add(
                db,
                HfFolderEntry,
                space_id=space_id,
                folder_id=target_id,
                asset_id=copied.asset_id,
                revision=1,
                order_num=entry.order_num,
                **audit,
            )

        if entry_id is not None:
            return copied_entry

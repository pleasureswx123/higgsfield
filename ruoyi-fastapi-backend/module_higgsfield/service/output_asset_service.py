"""归档作品转素材：独立身份、共享不可变文件、保留来源，单事务落库。"""
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class OutputAssetService:
    @staticmethod
    async def create(db, user, identity, payload, key):
        path = f'/outputs/{identity}/to-asset'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            # 沿用归档任务→输出锁序，避免与归档补偿倒置。
            job, output = await GeneratedOutputDao.locked(db, identity)
            await OutputReadService.authorized(db, user, identity)
            await OutputReadService.authorized(db, user, identity, 'asset:reference')
            project_id = int(payload.project_id)
            await WorkspaceService.authorize(db, user, project_id, 'asset:create', write=True)
            space = await FolderDao.space(db, project_id, lock=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            file = await GeneratedOutputDao.file(db, output.file_id) if output.file_id else None
            if output.kind not in {'image', 'video'} or output.archive_state != '2' or file is None or file.state != '1':
                WorkspaceService.conflict('FILE_NOT_READY', '作品尚未归档为可用图片或视频')
            if file.mime_type not in {'image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm'} or file.mime_type.split('/')[0] != output.kind:
                WorkspaceService.conflict('ASSET_FORMAT_UNSUPPORTED', '作品文件格式与素材类型不匹配')
            folder_id = int(payload.folder_id) if payload.folder_id else None
            await FolderService.check_target(db, space.space_id, folder_id, 'media')
            audit = WriteService.audit(user)
            asset = await AssetDao.add(db, HfAsset, space_id=space.space_id, asset_name=payload.name,
                media_type=output.kind, create_user_id=user.user.user_id, revision=1, del_flag='0', **audit)
            version = await AssetDao.add(db, HfAssetVersion, asset_id=asset.asset_id, version_no=1,
                file_id=file.file_id, source_output_id=output.output_id, create_user_id=user.user.user_id,
                media_metadata={'mimeType': file.mime_type, 'width': file.width, 'height': file.height,
                    'seconds': str(file.seconds) if file.seconds is not None else None}, **audit)
            asset.current_version_id = version.version_id
            await AssetDao.add(db, HfFolderEntry, space_id=space.space_id, folder_id=folder_id,
                asset_id=asset.asset_id, revision=1, **audit)
            await AssetDao.flush(db)
            result = await AssetService.result(db, asset)
            await AssetDao.add(db, HfAuditLog, project_id=project_id, actor_id=user.user.user_id,
                actor_kind='user', object_type='asset', object_id=str(asset.asset_id), action='from_output',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'source': {'outputId': str(output.output_id), 'jobId': str(job.job_id)},
                              'after': {'assetId': str(asset.asset_id), 'versionId': str(version.version_id)}}, **audit)
            return await WriteService.finish(db, user, path, key, data, result, 'asset', asset.asset_id)
        except Exception:
            await db.rollback()
            raise

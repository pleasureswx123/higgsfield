"""生成图片和视频自动成为提交目录素材；由持有任务及输出锁的归档事务调用。"""

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry


class GeneratedAssetBindingService:
    @staticmethod
    async def bind(db, job, output, file, now, worker):
        if job.input_snapshot.get('billingMode') != 'actual_usage' or output.kind not in {'image', 'video'}:
            return
        if output.actual_metadata.get('assetId'):
            return
        space = await FolderDao.space(db, job.project_id, lock=True)
        folder_id = job.input_snapshot.get('folderId')
        folder_id = int(folder_id) if folder_id else None
        folder = await FolderDao.get(db, folder_id) if folder_id else None
        if space is None or (folder_id and (folder is None or folder.del_flag != '0' or folder.space_id != space.space_id or folder.folder_kind != 'media')):
            # 目录在生成期间删除时保留已归档输出，不擅自改存其他目录。
            output.actual_metadata = {**output.actual_metadata, 'destinationIssue': '原目录不可用，请从任务详情另存素材'}
            return
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        label = '图片' if output.kind == 'image' else '视频'
        name = f'生成{label}-{job.job_id}-{output.ordinal + 1}.{file.mime_type.split("/")[1]}'
        metadata = {'mimeType': file.mime_type, 'width': file.width, 'height': file.height}
        if file.seconds is not None:
            metadata['seconds'] = str(file.seconds)
        asset = await AssetDao.add(db, HfAsset, space_id=space.space_id, asset_name=name,
            media_type=output.kind, create_user_id=job.actor_id, revision=1, del_flag='0', **audit)
        version = await AssetDao.add(db, HfAssetVersion, asset_id=asset.asset_id, version_no=1,
            file_id=file.file_id, source_output_id=output.output_id, create_user_id=job.actor_id,
            media_metadata=metadata, **audit)
        asset.current_version_id = version.version_id
        await AssetDao.add(db, HfFolderEntry, space_id=space.space_id, folder_id=folder_id,
            asset_id=asset.asset_id, revision=1, **audit)
        output.actual_metadata = {**output.actual_metadata, 'assetId': str(asset.asset_id)}

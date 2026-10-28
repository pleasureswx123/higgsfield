"""只读取调用方已授权原文件对应的就绪缩略图。"""

from module_higgsfield.dao.media_derivative_dao import MediaDerivativeDao
from module_higgsfield.service.image_thumbnail_service import ImageThumbnailService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.stored_media_service import StoredMediaService


class ThumbnailReadService:
    @staticmethod
    async def stream(db, source, range_header=None, head=False, storage=None):
        # 调用前必须完成素材/作品权限检查，不能开放按文件编号读取的路由。
        if source.state == '1' and source.mime_type in {'video/mp4', 'video/webm'}:
            from module_higgsfield.service.video_poster_service import VideoPosterService
            key, digest = source.storage_key, source.sha256
            # 截帧属于文件处理，先结束读取事务再在线程中执行。
            await db.rollback()
            return await VideoPosterService.stream(key, digest, head, storage)
        if source.state != '1' or source.mime_type not in {'image/png', 'image/jpeg', 'image/webp'}:
            WorkspaceService.conflict('THUMBNAIL_NOT_READY', '该文件没有可用的图片缩略图')
        derived = await MediaDerivativeDao.ready(db, source.file_id, ImageThumbnailService.recipe)
        if derived is None:
            WorkspaceService.conflict('THUMBNAIL_NOT_READY', '图片缩略图尚未生成或不可用')
        return await StoredMediaService.stream(db, derived.storage_key, derived.byte_size,
            derived.mime_type, 'thumbnail.webp', range_header, head=head, storage=storage)

"""缩略图短事务调度与登记；解码和存储写入不在此服务事务内执行。"""
from datetime import timedelta
from module_higgsfield.dao.media_derivative_dao import MediaDerivativeDao as Dao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.entity.vo.archive_file_vo import ArchiveFileFacts
from module_higgsfield.service.image_thumbnail_service import ImageThumbnailService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class MediaDerivativeService:
    recipe = ImageThumbnailService.recipe
    errors = {'THUMBNAIL_SOURCE_INVALID', 'THUMBNAIL_TOO_LARGE', 'MEDIA_INVALID',
              'STORAGE_UNAVAILABLE', 'THUMBNAIL_SOURCE_UNAVAILABLE', 'THUMBNAIL_PROCESSING_FAILED'}

    @staticmethod
    def worker(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            raise ValueError('工作器身份须为1至64字符')

    @staticmethod
    def fail(code, message):
        WorkspaceService.conflict(code, message)

    @classmethod
    async def enqueue(cls, db, source_id, actor='thumbnail-worker'):
        cls.worker(actor)
        try:
            source = await Dao.file(db, source_id)
            if not source or source.state != '1' or source.mime_type not in {'image/png', 'image/jpeg', 'image/webp'}:
                cls.fail('THUMBNAIL_SOURCE_INVALID', '源文件不是就绪图片')
            row = await Dao.enqueue(db, source_id, cls.recipe, await Dao.now(db), actor)
            result = row.derivative_id
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def claim(cls, db, worker, seconds=120):
        cls.worker(worker)
        if type(seconds) is not int or not 5 <= seconds <= 300:
            raise ValueError('租约期限须为5至300秒')
        try:
            now = await Dao.now(db)
            row = await Dao.candidate(db, cls.recipe, now)
            if not row:
                await db.commit()
                return None
            source = await Dao.file(db, row.source_file_id)
            if not source or source.state != '1':
                # 隔离/丢失文件恢复就绪后可继续；等待期间不读取文件，不改变源状态。
                row.state, row.error_code = '3', 'THUMBNAIL_SOURCE_UNAVAILABLE'
                row.next_action_time = now + timedelta(seconds=300)
                row.lease_owner = row.lease_until = None
                row.revision += 1
                row.update_by, row.update_time = worker, now
                await db.commit()
                return None
            row.state, row.lease_owner, row.lease_until = '1', worker, now + timedelta(seconds=seconds)
            row.revision += 1
            row.attempts += 1
            row.update_by, row.update_time = worker, now
            result = {'id': row.derivative_id, 'revision': row.revision, 'recipe': row.recipe,
                      'sourceFileId': source.file_id, 'storageKey': source.storage_key,
                      'sha256': source.sha256, 'byteSize': source.byte_size, 'mimeType': source.mime_type}
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def complete(cls, db, identity, worker, revision, facts):
        cls.worker(worker)
        verified = ArchiveFileFacts.model_validate(facts)
        if verified.mime_type != 'image/webp' or max(verified.width, verified.height) > ImageThumbnailService.max_edge or verified.byte_size > ImageThumbnailService.max_output_bytes:
            raise ValueError('缩略图事实不符合当前配方')
        try:
            row = await Dao.locked(db, identity)
            if row and row.state == '2':
                existing = await Dao.file(db, row.derived_file_id)
                if existing and all(getattr(existing, key) == value for key, value in verified.model_dump().items()):
                    await db.commit()
                    return existing.file_id
                cls.fail('THUMBNAIL_IMMUTABLE', '已登记缩略图不能更换')
            now = await Dao.now(db)
            cls.check_lease(row, worker, revision, now)
            source = await Dao.file(db, row.source_file_id, lock=True)
            if not source or source.state != '1':
                cls.fail('THUMBNAIL_SOURCE_UNAVAILABLE', '源文件暂不可用，等待恢复后重试')
            if source.storage_key == verified.storage_key:
                cls.fail('THUMBNAIL_SOURCE_INVALID', '派生键不能与源文件相同')
            file = await AssetDao.add(db, HfStoredFile, **verified.model_dump(), state='1',
                create_by=worker, update_by=worker, create_time=now, update_time=now)
            row.derived_file_id, row.state = file.file_id, '2'
            row.lease_owner = row.lease_until = row.error_code = None
            row.revision += 1
            row.update_by, row.update_time = worker, now
            result = file.file_id
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @classmethod
    def check_lease(cls, row, worker, revision, now):
        if not row or row.state != '1' or row.revision != revision or row.lease_owner != worker or row.lease_until <= now:
            cls.fail('THUMBNAIL_LEASE_LOST', '缩略图租约失效，旧执行者不能写回')

    @classmethod
    async def failure(cls, db, identity, worker, revision, code):
        cls.worker(worker)
        code = code if code in cls.errors else 'THUMBNAIL_PROCESSING_FAILED'
        try:
            row = await Dao.locked(db, identity)
            now = await Dao.now(db)
            cls.check_lease(row, worker, revision, now)
            row.state = '4' if code in {'THUMBNAIL_SOURCE_INVALID', 'THUMBNAIL_TOO_LARGE', 'MEDIA_INVALID'} else '3'
            row.error_code = code
            row.lease_owner = row.lease_until = None
            row.next_action_time = now + timedelta(seconds=min(300, 15 * 2 ** min(row.attempts, 4)))
            row.revision += 1
            row.update_by, row.update_time = worker, now
            await db.commit()
        except Exception:
            await db.rollback()
            raise

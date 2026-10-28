"""已授权持久文件的流式读取，文件IO前释放数据库事务。"""

import os
from starlette.concurrency import run_in_threadpool
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from utils.file_util import FileUtil
from utils.upload_util import UploadUtil


class StoredMediaService:
    @staticmethod
    async def stream(db, key, size, mime, name, range_header=None, download=False, head=False, storage=None, on_ready=None):
        byte_range = FileUtil.parse_byte_range(range_header, size)
        headers = UploadUtil.build_download_headers(name, byte_range, True)
        if not download:
            headers['Content-Disposition'] = 'inline'
        headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        await db.rollback()
        storage = storage or StorageService()
        context = storage.open_key(key)
        handle = await run_in_threadpool(context.__enter__)
        try:
            if os.fstat(handle.fileno()).st_size != size:
                WorkspaceService.conflict('FILE_NOT_READY', '文件内容大小异常，请联系管理员')
            await run_in_threadpool(handle.seek, byte_range.start)
            # 文件确实可读后记录授权事实，审计失败时关闭句柄并拒绝响应。
            if not head and on_ready is not None:
                await on_ready(byte_range)
        except BaseException:
            await run_in_threadpool(context.__exit__, None, None, None)
            raise
        if head:
            await run_in_threadpool(context.__exit__, None, None, None)
            return None, headers, mime, 206 if byte_range.is_partial else 200

        async def chunks():
            remaining = byte_range.length
            try:
                while remaining:
                    chunk = await run_in_threadpool(handle.read, min(1024 * 1024, remaining))
                    if not chunk:
                        raise OSError('媒体读取中断')
                    remaining -= len(chunk)
                    yield chunk
            finally:
                await run_in_threadpool(context.__exit__, None, None, None)

        return chunks(), headers, mime, 206 if byte_range.is_partial else 200

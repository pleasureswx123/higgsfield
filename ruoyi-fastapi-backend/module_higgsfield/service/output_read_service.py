"""生成输出的授权投影与持久媒体读取。"""

from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.stored_media_service import StoredMediaService
from module_higgsfield.entity.vo.generated_output_vo import OutputMetadata
from utils.time_util import TimezoneUtil


class OutputReadService:
    @staticmethod
    async def authorized(db, user, identity, permission='asset:read'):
        output = await GeneratedOutputDao.get(db, identity)
        if output is None or output.del_flag != '0':
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '输出不存在或无权访问')
        job = await GenerationReadDao.job(db, output.job_id)
        if job is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '输出不存在或无权访问')
        project, _, allowed = await WorkspaceService.authorize(db, user, job.project_id, permission, owner_id=job.actor_id)
        if project.status != '0':
            allowed = allowed - {'content:review'}
        return output, allowed

    @classmethod
    async def get(cls, db, user, identity):
        output, allowed = await cls.authorized(db, user, identity)
        # 元数据按公开字段投影，不把未来内部字段和源地址自动扩散给客户端。
        metadata = {
            key: value
            for key, value in output.actual_metadata.items()
            if key in {'width', 'height', 'durationSeconds', 'format', 'revisedPrompt'}
        }
        metadata = OutputMetadata.model_validate(metadata).model_dump(by_alias=True, exclude_none=True)
        result = {
            'id': str(output.output_id),
            'jobId': str(output.job_id),
            'ordinal': output.ordinal,
            'kind': output.kind,
            'revision': str(output.revision),
            'workStatus': ('none', 'working', 'review', 'approved', 'rejected')[int(output.work_status)],
            'archiveState': (
                'not_started',
                'archiving',
                'archived',
                'archive_failed',
                'source_expired',
                'not_applicable',
            )[int(output.archive_state)],
            'actualMetadata': metadata,
            'allowedActions': ['output:archive'] if (
                'output:archive' in allowed and output.archive_state == '3'
                and output.kind in {'image', 'video'} and output.source_url_ciphertext is not None
                and (output.source_expires_time is None or output.source_expires_time > TimezoneUtil.utc_now())
            ) else [],
        }
        if output.kind == 'text':
            result['text'] = output.text_content
        if output.archive_state == '2':
            file = await AssetDao.file(db, output.file_id)
            if file:
                result['file'] = {
                    'id': str(file.file_id),
                    'mimeType': file.mime_type,
                    'byteSize': str(file.byte_size),
                    'width': file.width,
                    'height': file.height,
                    'seconds': str(file.seconds) if file.seconds is not None else None,
                    'state': 'ready' if file.state == '1' else 'unavailable',
                }
                if file.state == '1':
                    if 'content:review' in allowed and output.kind in {'image', 'video'}:
                        result['allowedActions'].append('output:work-status')
                    result['previewUrl'] = f'/api/v1/outputs/{output.output_id}/preview'
                    if ('asset:reference' in allowed and output.kind in {'image', 'video'}
                            and file.mime_type in {'image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm'}
                            and file.mime_type.split('/')[0] == output.kind):
                        result['allowedActions'].append('output:to-asset')
                    if 'asset:download' in allowed:
                        result['downloadUrl'] = f'/api/v1/outputs/{output.output_id}/download'
                        result['allowedActions'].append('asset:download')
        return result

    @classmethod
    async def media(cls, db, user, identity, range_header=None, download=False, head=False, storage=None, thumbnail=False):
        output, _ = await cls.authorized(db, user, identity, 'asset:download' if download else 'asset:read')
        file = await AssetDao.file(db, output.file_id) if output.file_id else None
        if output.archive_state != '2' or file is None or file.state != '1':
            WorkspaceService.conflict('FILE_NOT_READY', '输出尚未归档或文件不可用')
        if thumbnail:
            from module_higgsfield.service.thumbnail_read_service import ThumbnailReadService
            return await ThumbnailReadService.stream(db, file, range_header, head, storage)
        return await StoredMediaService.stream(
            db,
            file.storage_key,
            file.byte_size,
            file.mime_type,
            f'output-{output.output_id}',
            range_header,
            download,
            head,
            storage,
        )

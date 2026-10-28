"""归档阶段短事务；文件下载、校验及NAS落盘在调用方事务外执行。"""

from datetime import timedelta
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.provider_response_dao import ProviderResponseDao
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.entity.vo.archive_file_vo import ArchiveFileFacts
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class OutputArchiveService:
    @classmethod
    async def register_download(cls, db, output_id, *, revision, worker, facts):
        """文件登记、输出绑定和事件同事务提交；失败不留下就绪文件记录。

        仅接收下载器完成真实媒体校验后的事实。提交结果不确定时，调用方不得删除
        磁盘文件，应先查询输出及存储键的绑定事实，避免误删已经提交的归档。
        """
        JobLeaseService.validate_worker(worker)
        verified = ArchiveFileFacts.model_validate(facts)
        try:
            # 先沿用任务→输出锁顺序，防止多个登记者交错插入文件。
            job, output = await GeneratedOutputDao.locked(db, output_id)
            if job is None or output is None:
                WorkspaceService.conflict('OUTPUT_ARCHIVE_UNAVAILABLE', '输出不存在')
            if output.archive_state == '2':
                existing = await GeneratedOutputDao.file(db, output.file_id)
                if existing is None or any(
                    getattr(existing, key) != value for key, value in verified.model_dump().items()
                ):
                    WorkspaceService.conflict('OUTPUT_ARCHIVE_IMMUTABLE', '已归档输出不能更换文件')
                return await cls.mutate(
                    db, output_id, revision=revision, action='complete', worker=worker, file_id=existing.file_id
                )
            now = await JobLeaseDao.now(db)
            file = await AssetDao.add(
                db,
                HfStoredFile,
                **verified.model_dump(),
                state='1',
                create_by=worker,
                update_by=worker,
                create_time=now,
                update_time=now,
            )
            return await cls.mutate(
                db, output_id, revision=revision, action='complete', worker=worker, file_id=file.file_id
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def mutate(cls, db, output_id, *, revision, action, worker, file_id=None, delay_seconds=60):
        """内部归档工作进程入口；输出revision充当阶段栅栏，不能使用任务生成租约。

        begin占用阶段并设置截止时间；超时可重新领取但旧revision不能写回。
        complete仅接受已验证就绪的同类型存储文件；重复完成不允许替换文件。
        """
        JobLeaseService.validate_worker(worker)
        if action not in {'begin', 'complete', 'fail', 'expire', 'renew'}:
            raise ValueError('不支持的归档动作')
        if type(delay_seconds) is not int or not 5 <= delay_seconds <= 300:
            raise ValueError('归档占用或重试延迟必须为5至300秒')
        if (action == 'complete') != (file_id is not None):
            raise ValueError('完成归档必须且仅能提供文件编号')
        try:
            job, output = await GeneratedOutputDao.locked(db, output_id)
            if job is None or output is None or output.del_flag != '0' or output.kind == 'text':
                WorkspaceService.conflict('OUTPUT_ARCHIVE_UNAVAILABLE', '输出不存在、已删除或无需归档')
            now = await JobLeaseDao.now(db)
            if output.archive_state == '2':
                if action == 'complete' and output.file_id == file_id:
                    result = {
                        'outputId': str(output.output_id),
                        'revision': str(output.revision),
                        'archiveState': 'archived',
                    }
                    await db.commit()
                    return result
                WorkspaceService.conflict('OUTPUT_ARCHIVE_IMMUTABLE', '已归档输出不能更换文件或重置状态')
            if output.revision != revision:
                WorkspaceService.conflict('OUTPUT_REVISION_CHANGED', '归档阶段已变化，旧执行者不能写回')
            if action == 'begin':
                if output.archive_state == '1' and (output.next_retry_time is None or output.next_retry_time > now):
                    WorkspaceService.conflict('OUTPUT_ARCHIVE_BUSY', '输出正在归档')
                if output.archive_state not in {'0', '1', '3'}:
                    WorkspaceService.conflict('OUTPUT_ARCHIVE_UNAVAILABLE', '当前输出源不可归档')
                if output.archive_state in {'0', '3'} and output.next_retry_time and output.next_retry_time > now:
                    WorkspaceService.conflict('OUTPUT_ARCHIVE_NOT_DUE', '尚未到归档重试时间')
                if output.source_expires_time and output.source_expires_time <= now:
                    output.archive_state, output.next_retry_time = '4', None
                else:
                    if output.source_url_ciphertext is None:
                        evidence = (
                            await ProviderResponseDao.for_completed_image(db, job.job_id)
                            if output.kind == 'image'
                            else None
                        )
                        if evidence is None:
                            WorkspaceService.conflict('OUTPUT_SOURCE_MISSING', '归档缺少已保存的媒体源')
                    output.archive_state, output.next_retry_time = '1', now + timedelta(seconds=delay_seconds)
            else:
                if output.archive_state != '1' or output.next_retry_time is None or output.next_retry_time <= now:
                    WorkspaceService.conflict('OUTPUT_ARCHIVE_LEASE_LOST', '归档占用已失效，请重新领取')
                if action == 'renew':
                    # 续期不改变内容事实或版本，长文件传输可持续维护原阶段栅栏。
                    output.next_retry_time = now + timedelta(seconds=delay_seconds)
                    result = {
                        'outputId': str(output.output_id),
                        'revision': str(output.revision),
                        'archiveState': 'archiving',
                    }
                    await db.commit()
                    return result
                if action == 'complete':
                    file = await GeneratedOutputDao.file(db, file_id)
                    if file is None or file.state != '1' or not file.mime_type.startswith(output.kind + '/'):
                        WorkspaceService.conflict('OUTPUT_FILE_NOT_READY', '归档文件不存在、不可用或媒体类型不匹配')
                    output.archive_state, output.file_id, output.next_retry_time = '2', file_id, None
                    # 以实际已校验文件补齐尺寸和格式，保留优化提示词等原有事实。
                    metadata = dict(output.actual_metadata)
                    metadata['format'] = file.mime_type.split('/')[1]
                    for name in ('width', 'height'):
                        if getattr(file, name) is not None:
                            metadata[name] = getattr(file, name)
                    if file.seconds is not None:
                        metadata['durationSeconds'] = str(file.seconds)
                    output.actual_metadata = metadata
                else:
                    output.archive_state = '3' if action == 'fail' else '4'
                    output.next_retry_time = now + timedelta(seconds=delay_seconds) if action == 'fail' else None
            output.revision += 1
            output.update_time, output.update_by = now, worker
            job.revision += 1
            job.event_sequence += 1
            job.update_time, job.update_by = now, worker
            await JobEventDao.output(db, job, output, now, worker)
            result = {
                'outputId': str(output.output_id),
                'revision': str(output.revision),
                'archiveState': (
                    'not_started',
                    'archiving',
                    'archived',
                    'archive_failed',
                    'source_expired',
                    'not_applicable',
                )[int(output.archive_state)],
            }
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

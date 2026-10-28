"""归档重试仅重新调度已有失败输出，不重提供应商生成任务。"""

from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.admin_scope_service import AdminScopeService


class GenerationArchiveRetryService:
    @classmethod
    async def retry(cls, db, user, identity, payload, key):
        return await cls._retry(db, user, identity, payload, key, managed=False)

    @classmethod
    async def retry_managed(cls, db, user, identity, payload, key):
        return await cls._retry(db, user, identity, payload, key, managed=True)

    @classmethod
    async def _retry(cls, db, user, identity, payload, key, *, managed):
        path = f'/generation-incidents/{identity}/actions' if managed else f'/generations/{identity}/retry-archive'
        prefix = '/api/admin/v1' if managed else '/api/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            job = await GenerationReadDao.job(db, identity, lock='write')
            if job is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或无权访问')
            if managed:
                await AdminScopeService.project(db, user, job.project_id, 'operations:recover')
            else:
                await WorkspaceService.authorize(db, user, job.project_id, 'output:archive', owner_id=job.actor_id)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(job, payload.revision)
            now = await JobLeaseDao.now(db)
            rows = await GeneratedOutputDao.for_job(db, identity)
            selected = set(map(int, payload.output_ids)) if not managed and payload.output_ids is not None else None
            candidates = [row for row in rows if row.output_id in selected] if selected is not None else [
                row for row in rows if row.del_flag == '0' and row.archive_state == '3'
            ]
            if not candidates or (selected is not None and len(candidates) != len(selected)):
                WorkspaceService.conflict('OUTPUT_RETRY_UNAVAILABLE', '没有可重试的失败输出或输出不属于此任务')
            # 任务行锁与归档执行者保持一致；先校验全部输出，再原子调度。
            for row in candidates:
                if (row.del_flag != '0' or row.archive_state != '3' or row.kind not in {'image', 'video'}
                        or row.source_url_ciphertext is None
                        or (row.source_expires_time is not None and row.source_expires_time <= now)):
                    WorkspaceService.conflict('OUTPUT_RETRY_UNAVAILABLE', '仅能重试源仍有效的失败媒体输出')
            for row in candidates:
                row.archive_state, row.next_retry_time = '0', now
                row.revision += 1
                row.update_by, row.update_time = user.user.user_name, now
                job.event_sequence += 1
                await JobEventDao.output(db, job, row, now, user.user.user_name)
            job.revision += 1
            job.update_by, job.update_time = user.user.user_name, now
            receipt = {'jobId': str(identity), 'revision': str(job.revision), 'accepted': True,
                       'outputIds': [str(row.output_id) for row in candidates]}
            await PriceSourceDao.audit(db, dict(
                actor_id=user.user.user_id, actor_kind='user', project_id=job.project_id,
                object_type='creation_job', object_id=str(identity), action='retry_archive',
                request_id=WriteService.digest({'prefix': prefix, 'path': path, 'key': key}),
                reason=payload.reason if managed else None,
                before_after=receipt | ({'evidenceRef': payload.evidence_ref} if managed and payload.evidence_ref else {}),
                **WriteService.audit(user),
            ))
            return await WriteService.finish(db, user, path, key, data, receipt, 'generation', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise

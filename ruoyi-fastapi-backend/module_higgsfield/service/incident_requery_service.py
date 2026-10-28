"""重新查询仅提前已有核查阶段，不回退到准备或提交阶段。"""
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class IncidentRequeryService:
    @staticmethod
    def eligible(job, now):
        if job.lease_until is not None and job.lease_until > now:
            return False
        # 提交未知只核查本地响应证据，已有视频任务编号才调用供应商轮询。
        return ((job.kind in {'image', 'video'} and job.orchestration_state == '3'
                 and not job.upstream_task_id) or
                (job.kind == 'video' and job.orchestration_state == '4'
                 and job.upstream_state in {'1', '2', '6'} and bool(job.upstream_task_id)))

    @classmethod
    async def requery(cls, db, user, identity, payload, key):
        path, prefix = f'/generation-incidents/{identity}/actions', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            job = await GenerationReadDao.job(db, identity, lock='write')
            if job is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或不在管理范围内')
            await AdminScopeService.project(db, user, job.project_id, 'operations:recover')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(job, payload.revision)
            now = await JobLeaseDao.now(db)
            if not cls.eligible(job, now):
                WorkspaceService.conflict('INCIDENT_REQUERY_UNAVAILABLE', '当前阶段不支持重新查询或仍有执行者持有租约')
            job.next_action_time = now
            job.lease_owner = None
            job.lease_until = None
            job.fencing_token += 1
            job.revision += 1
            job.event_sequence += 1
            job.update_time, job.update_by = now, user.user.user_name
            await JobEventDao.state(db, job, now, user.user.user_name)
            receipt = {'jobId': str(identity), 'revision': str(job.revision), 'accepted': True, 'action': 'requery'}
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user', project_id=job.project_id,
                object_type='creation_job', object_id=str(identity), action='requery', reason=payload.reason,
                request_id=WriteService.digest({'prefix': prefix, 'path': path, 'key': key}),
                before_after=receipt | ({'evidenceRef': payload.evidence_ref} if payload.evidence_ref else {}),
                **WriteService.audit(user)))
            return await WriteService.finish(db, user, path, key, data, receipt, 'generation', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise

"""未提交生成任务的本地取消、预占释放及事件原子提交。"""

from fastapi.encoders import jsonable_encoder
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.service.budget_release_service import BudgetReleaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class GenerationCancelService:
    @classmethod
    async def cancel(cls, db, user, identity, payload, key):
        path, data = f'/generations/{identity}/cancel', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            job = await GenerationReadDao.job(db, identity, lock='write')
            if job is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或无权访问')
            await WorkspaceService.authorize(db, user, job.project_id, 'generation:cancel', owner_id=job.actor_id)
            await WorkspaceService.authorize(db, user, job.project_id, 'generation:read', owner_id=job.actor_id)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                # 重放也按当前权限生成快照，不复用历史响应中的输出正文。
                task = await GenerationReadService.snapshot(db, user, identity)
                await db.commit()
                replay['data']['task'] = jsonable_encoder(task)
                return replay, True
            WorkspaceService.check_revision(job, payload.revision)
            if (
                job.orchestration_state not in {'0', '1'}
                or job.upstream_state != '0'
                or job.upstream_task_id
                or job.upstream_response_id
            ):
                WorkspaceService.conflict(
                    'GENERATION_LOCAL_CANCEL_UNAVAILABLE', '任务已进入提交或后续阶段，不能按未消费任务本地取消'
                )
            now = await JobLeaseDao.now(db)
            job.orchestration_state, job.cancel_state = '5', '2'
            job.finished_time = now
            job.next_action_time = None
            job.lease_owner = None
            job.lease_until = None
            job.fencing_token += 1
            job.revision += 1
            job.event_sequence += 1
            job.update_by, job.update_time = user.user.user_name, now
            # 保存点进入前flush取消事实，释放服务只接受数据库中明确的本地取消。
            await db.flush()
            await BudgetReleaseService.release_unsubmitted(db, user, identity, reason=payload.reason)
            await JobEventDao.state(db, job, now, user.user.user_name)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    object_type='creation_job',
                    project_id=job.project_id,
                    object_id=str(identity),
                    action='local_cancel',
                    reason=payload.reason,
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'revision': str(job.revision), 'cancelState': 'confirmed'},
                    **WriteService.audit(user),
                ),
            )
            task = await GenerationReadService.snapshot(db, user, identity)
            receipt = {'jobId': str(identity), 'accepted': True, 'mode': 'local', 'cancellationState': 'confirmed'}
            response, replayed = await WriteService.finish(db, user, path, key, data, receipt, 'generation', identity)
            response['data']['task'] = jsonable_encoder(task)
            return response, replayed
        except Exception:
            await db.rollback()
            raise

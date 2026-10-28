"""作品协作状态与不可删除的历史、实时事件同事务保存。"""
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.do.review_do import HfReviewEvent
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class OutputStatusService:
    STATUSES = ('none', 'working', 'review', 'approved', 'rejected')

    @classmethod
    async def update(cls, db, user, identity, payload, key):
        path, data = f'/outputs/{identity}/work-status', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            job, output = await GeneratedOutputDao.locked(db, identity)
            await OutputReadService.authorized(db, user, identity)
            await WorkspaceService.authorize(db, user, job.project_id, 'content:review', owner_id=job.actor_id, write=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(output, payload.revision)
            file = await GeneratedOutputDao.file(db, output.file_id) if output.file_id else None
            if output.kind not in {'image', 'video'} or output.archive_state != '2' or file is None or file.state != '1':
                WorkspaceService.conflict('FILE_NOT_READY', '作品尚未归档就绪，不能修改协作状态')
            previous = cls.STATUSES[int(output.work_status)]
            if previous != payload.work_status:
                audit = WriteService.audit(user)
                await AssetDao.add(db, HfReviewEvent, output_id=identity, actor_id=user.user.user_id,
                    from_status=previous, to_status=payload.work_status, reason=payload.reason.strip() or None, **audit)
                output.work_status = str(cls.STATUSES.index(payload.work_status))
                output.revision += 1
                output.update_time, output.update_by = audit['update_time'], audit['update_by']
                job.revision += 1
                job.event_sequence += 1
                job.update_time, job.update_by = audit['update_time'], audit['update_by']
                await JobEventDao.output(db, job, output, audit['update_time'], audit['update_by'])
            result = await OutputReadService.get(db, user, identity)
            return await WriteService.finish(db, user, path, key, data, result, 'output', identity)
        except Exception:
            await db.rollback()
            raise

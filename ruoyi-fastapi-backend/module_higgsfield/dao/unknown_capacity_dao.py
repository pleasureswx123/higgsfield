"""保护期结束后回收本地名额并留下不可删除审计，不改写供应商事实。"""
from datetime import timedelta
from sqlalchemy import select, or_
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.provider_call_do import HfProviderCall
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion
from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.dao.job_event_dao import JobEventDao


class UnknownCapacityDao:
    @staticmethod
    async def release_expired(db, now, worker, hold_seconds):
        # 先锁任务再锁调用，与执行结果落库顺序一致；仍在自动核查的任务不回收。
        jobs = (await db.scalars(select(HfCreationJob).where(
            HfCreationJob.orchestration_state == '3', HfCreationJob.upstream_state == '6',
            HfCreationJob.next_action_time.is_(None),
            or_(HfCreationJob.lease_until.is_(None), HfCreationJob.lease_until <= now),
            select(HfProviderCall.call_id).where(
                HfProviderCall.job_id == HfCreationJob.job_id,
                HfProviderCall.state.in_(('2', '3')), HfProviderCall.acceptance == 'unknown',
                HfProviderCall.finished_time <= now - timedelta(seconds=hold_seconds),
                HfProviderCall.request_metadata['capacityReleasedAt'].astext.is_(None),
            ).exists(),
        ).order_by(HfCreationJob.job_id).limit(100).with_for_update(skip_locked=True))).all()
        released = 0
        for job in jobs:
            calls = (await db.scalars(select(HfProviderCall).where(
                HfProviderCall.job_id == job.job_id,
                HfProviderCall.operation.in_(('image', 'video_submit', 'chat')),
            ).with_for_update(skip_locked=True))).all()
            for call in calls:
                if await UnknownCapacityDao.release_call(db, call, now, worker, hold_seconds, job.project_id):
                    released += 1
                    job.event_sequence += 1
                    job.revision += 1
                    job.update_by, job.update_time = worker, now
                    await JobEventDao.state(db, job, now, worker, stage='unknown_capacity_released')
        tests = (await db.scalars(select(HfProviderCall).where(
            HfProviderCall.operation == 'test', HfProviderCall.state.in_(('2', '3')),
            HfProviderCall.acceptance == 'unknown',
            HfProviderCall.finished_time <= now - timedelta(seconds=hold_seconds),
            HfProviderCall.request_metadata['capacityReleasedAt'].astext.is_(None),
        ).order_by(HfProviderCall.call_id).limit(100).with_for_update(skip_locked=True))).all()
        for call in tests:
            released += int(await UnknownCapacityDao.release_call(db, call, now, worker, hold_seconds, None))
        await db.flush()
        return released

    @staticmethod
    async def release_call(db, call, now, worker, hold_seconds, project_id):
        if (call.state not in ('2', '3') or call.acceptance != 'unknown' or not call.finished_time
                or call.request_metadata.get('capacityReleasedAt')):
            return False
        config = await db.scalar(select(HfProviderConnectionVersion.config)
            .join(HfCredentialVersion, HfCredentialVersion.connection_version_id ==
                  HfProviderConnectionVersion.connection_version_id)
            .where(HfCredentialVersion.credential_version_id == call.credential_version_id))
        # 配置缺失或无效时保守保留；不能用客户端超时推断供应商已停止。
        duration = (config or {}).get('taskTimeoutSeconds', (config or {}).get('task_timeout_seconds'))
        if type(duration) is not int or duration <= 0 or call.started_time is None:
            return False
        deadline = max(call.finished_time + timedelta(seconds=hold_seconds),
                       call.started_time + timedelta(seconds=duration + 60))
        if now < deadline:
            return False
        call.request_metadata = {**call.request_metadata, 'capacityReleasedAt': now.isoformat(),
            'capacityReleaseEvidence': '未知结果保护期到期，仅回收本地调度名额；上游结果与费用仍待核实',
            'capacityReleasePolicy': {'holdSeconds': hold_seconds, 'deadline': deadline.isoformat()}}
        call.update_by, call.update_time = worker, now
        db.add(HfAuditLog(actor_kind='system', project_id=project_id, object_type='provider_call',
            object_id=str(call.call_id), action='release_unknown_capacity',
            request_id=f'unknown-capacity-{call.call_id}',
            before_after={'capacityReserved': False, 'acceptance': 'unknown',
                          'deadline': deadline.isoformat()},
            reason='保护期到期，自动恢复本地队列；不重发请求、不确认成功失败或费用',
            create_by=worker, update_by=worker, create_time=now, update_time=now))
        return True

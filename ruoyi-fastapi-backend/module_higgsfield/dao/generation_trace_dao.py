"""读取已有执行事实，不触发任务调度或供应商请求。"""
from sqlalchemy import select
from module_higgsfield.entity.do.outbox_do import HfTaskEvent
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class GenerationTraceDao:
    @staticmethod
    async def latest_stage(db, job_id):
        return await db.scalar(select(HfTaskEvent.payload['stage'].astext).where(
            HfTaskEvent.job_id == job_id, HfTaskEvent.payload.has_key('stage'),
        ).order_by(HfTaskEvent.sequence.desc()).limit(1))

    @staticmethod
    async def events(db, job_id):
        rows = await db.scalars(select(HfTaskEvent).where(
            HfTaskEvent.job_id == job_id,
            HfTaskEvent.event_type.in_(('task.state', 'output.state', 'task.problem')),
            ~HfTaskEvent.payload.has_key('downloadProgress'),
        ).order_by(HfTaskEvent.sequence.desc()).limit(200))
        return list(reversed(rows.all()))

    @staticmethod
    async def calls(db, job_id):
        rows = await db.scalars(select(HfProviderCall).where(
            HfProviderCall.job_id == job_id,
        ).order_by(HfProviderCall.call_id.desc()).limit(20))
        return list(reversed(rows.all()))

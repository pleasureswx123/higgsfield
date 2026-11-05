"""依据发送事实及管理员恢复事件计算自动核查窗口，不修改固定输入。"""
from sqlalchemy import select, func
from module_higgsfield.entity.do.outbox_do import HfTaskEvent
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class TrackingWindowDao:
    @staticmethod
    async def start(db, job):
        reset = await db.scalar(select(func.max(HfTaskEvent.occurred_time)).where(
            HfTaskEvent.job_id == job.job_id, HfTaskEvent.payload['stage'].astext == 'manual_requery'))
        submitted = await db.scalar(select(func.min(HfProviderCall.started_time)).where(
            HfProviderCall.job_id == job.job_id, HfProviderCall.operation == 'video_submit'))
        return max(value for value in (reset, submitted or job.create_time) if value is not None)

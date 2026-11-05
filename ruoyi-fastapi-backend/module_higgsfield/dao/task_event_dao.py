"""按任务序号读取已提交事件，不依赖消息队列保存历史。"""

from sqlalchemy import select, func
from module_higgsfield.entity.do.outbox_do import HfTaskEvent
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class TaskEventDao:
    @staticmethod
    async def watermark(db, job_id):
        latest = select(func.max(HfProviderCall.update_time)).where(
            HfProviderCall.job_id == job_id).scalar_subquery()
        return (await db.execute(select(HfCreationJob.revision, HfCreationJob.event_sequence, latest)
                .where(HfCreationJob.job_id == job_id))).first()

    @staticmethod
    async def after(db, job_id, sequence, limit=100):
        return list(
            (
                await db.scalars(
                    select(HfTaskEvent)
                    .where(
                        HfTaskEvent.job_id == job_id,
                        HfTaskEvent.sequence > sequence,
                    )
                    .order_by(HfTaskEvent.sequence)
                    .limit(limit)
                )
            ).all()
        )

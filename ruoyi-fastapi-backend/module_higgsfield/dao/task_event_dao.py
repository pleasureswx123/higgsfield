"""按任务序号读取已提交事件，不依赖消息队列保存历史。"""

from sqlalchemy import select
from module_higgsfield.entity.do.outbox_do import HfTaskEvent


class TaskEventDao:
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

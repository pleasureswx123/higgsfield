"""事务内发布无业务正文的工作区变化通知；回滚不投递。"""
import json
from sqlalchemy import text


class ProjectActivityNotificationDao:
    @staticmethod
    async def publish(db, job, *, own_only=False):
        await db.execute(text("SELECT pg_notify('hf_activity_' || md5(current_schema()), :payload)"),
            {'payload': json.dumps({'project': str(job.project_id), 'actor': str(job.actor_id), 'ownOnly': own_only})})

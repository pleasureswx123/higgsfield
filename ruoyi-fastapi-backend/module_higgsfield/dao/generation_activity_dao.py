"""工作区状态批量读取，使用服务层实时计算的项目权限范围，不加任务行锁、不读取账单和媒体正文。"""

from sqlalchemy import func, select

from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.outbox_do import HfTaskEvent
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class GenerationActivityDao:
    @staticmethod
    async def read(db, actor_id, query, scope):
        visible = select(HfCreationJob).where(HfCreationJob.project_id == int(query.project_id))
        if scope == 'own':
            visible = visible.where(HfCreationJob.actor_id == actor_id)
        project = visible.where(GenerationReadDao.category_condition('active'))
        count = await db.scalar(select(func.count()).select_from(project.subquery()))
        mine = project.where(HfCreationJob.actor_id == actor_id)
        # 多取一条判断下一页，避免为个人列表再执行 COUNT。
        rows = list((await db.scalars(mine.order_by(HfCreationJob.job_id.desc())
                    .offset((query.page_num - 1) * 100).limit(101))).all())
        has_next = len(rows) > 100
        rows = rows[:100]
        if query.tracked_ids:
            tracked = visible.where(HfCreationJob.actor_id == actor_id)
            rows.extend((await db.scalars(tracked.where(HfCreationJob.job_id.in_(
                [int(value) for value in query.tracked_ids.split(',')])))).all())
        return list({row.job_id: row for row in rows}.values()), count, has_next

    @staticmethod
    async def execution(db, identities):
        if not identities:
            return {}, {}
        stages = (await db.execute(select(HfTaskEvent.job_id, HfTaskEvent.payload['stage'].astext)
            .where(HfTaskEvent.job_id.in_(identities), HfTaskEvent.payload.has_key('stage'))
            .distinct(HfTaskEvent.job_id).order_by(HfTaskEvent.job_id, HfTaskEvent.sequence.desc()))).all()
        # 只在服务内提取状态；不向客户端返回请求正文或供应商凭据。
        calls = (await db.execute(select(HfProviderCall.job_id, HfProviderCall.request_metadata)
            .where(HfProviderCall.job_id.in_(identities), HfProviderCall.operation.in_(('image', 'video_submit', 'video_poll')))
            .distinct(HfProviderCall.job_id).order_by(HfProviderCall.job_id, HfProviderCall.create_time.desc(), HfProviderCall.call_id.desc()))).all()
        return dict(stages), {row.job_id: row for row in calls}

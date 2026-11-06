"""复用若依参数配置及数据库事务锁，不依赖进程内计数。"""
from sqlalchemy import select, func, and_
from module_admin.entity.do.config_do import SysConfig
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class ProductionPolicyDao:
    @staticmethod
    async def settings(db, keys):
        return dict((await db.execute(select(SysConfig.config_key, SysConfig.config_value)
                    .where(SysConfig.config_key.in_(keys)).order_by(SysConfig.config_id))).all())

    @staticmethod
    async def queue_counts(db, actor_id, project_id):
        # 受理容量锁必须先于项目和路由锁；一直持有到任务与幂等回执提交。
        await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(
            func.concat(func.current_schema(), ':generation-admission'), 0))))
        return (await db.execute(select(
            func.count(),
            func.count().filter(HfCreationJob.actor_id == actor_id),
            func.count().filter(HfCreationJob.project_id == project_id),
        ).where(HfCreationJob.orchestration_state.in_(('0', '1', '2', '3', '4')),
            ~and_(HfCreationJob.orchestration_state == '3',
                select(HfProviderCall.call_id).where(
                    HfProviderCall.job_id == HfCreationJob.job_id,
                    HfProviderCall.request_metadata['capacityReleasedAt'].astext.is_not(None),
                ).exists())))).one()

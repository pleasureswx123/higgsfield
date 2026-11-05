"""跨项目、凭据版本和测试入口共用的短事务容量判断。"""
from sqlalchemy import select, func, or_, and_
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.routing_do import HfRoutingPolicy
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class ProductionCapacityDao:
    @staticmethod
    async def acquire(db, version_id, now, *, exclude_job_id=None):
        identity = await db.scalar(select(HfCredentialVersion.credential_id).where(
            HfCredentialVersion.credential_version_id == version_id))
        if identity is None:
            return False
        # 非阻塞事务锁避免与配置锁、任务锁形成等待环；未拿到锁留待下轮。
        if not await db.scalar(select(func.pg_try_advisory_xact_lock(func.hashtextextended(
                func.concat(func.current_schema(), ':generation-capacity:', str(identity)), 0)))):
            return False
        # 现有路由配置共同约束同一身份，取严格上限；无路由的新凭据测试串行执行。
        maximum = await db.scalar(select(func.min(HfRoutingPolicy.max_concurrency)).where(
            HfRoutingPolicy.credential_id == identity, HfRoutingPolicy.enabled == 'Y')) or 1
        versions = select(HfCredentialVersion.credential_version_id).where(
            HfCredentialVersion.credential_id == identity)
        await db.flush()
        occupied = await db.scalar(select(func.count()).select_from(HfCreationJob).where(
            HfCreationJob.credential_version_id.in_(versions),
            HfCreationJob.job_id != exclude_job_id if exclude_job_id is not None else True,
            ~select(HfProviderCall.call_id).where(
                HfProviderCall.job_id == HfCreationJob.job_id,
                HfProviderCall.request_metadata['capacityReleasedAt'].astext.is_not(None)).exists(),
            or_(HfCreationJob.orchestration_state.in_(('2', '3', '4')),
                HfCreationJob.upstream_state.in_(('1', '2', '6')),
                and_(HfCreationJob.orchestration_state.in_(('0', '1')), HfCreationJob.lease_until > now)),
        ))
        testing = await db.scalar(select(func.count()).select_from(HfProviderCall).where(
            HfProviderCall.credential_version_id.in_(versions),
            HfProviderCall.operation == 'test',
            HfProviderCall.request_metadata['capacityReleasedAt'].astext.is_(None),
            or_(HfProviderCall.state == '1', HfProviderCall.acceptance == 'unknown')))
        return occupied + testing < maximum

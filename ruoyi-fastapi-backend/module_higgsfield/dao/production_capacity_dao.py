"""跨项目、凭据版本和测试入口共用的短事务容量判断。"""
from sqlalchemy import select, func, or_, and_, text
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.routing_do import HfRoutingPolicy
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class ProductionCapacityDao:
    @staticmethod
    async def waiting_reasons(db, rows):
        """批量读取排队原因；只返回原因代码，不泄露其他项目的任务身份。"""
        waiting = [row for row in rows if row.orchestration_state == '0' and not row.lease_owner]
        if not waiting:
            return {}
        result = await db.execute(text('''
            WITH identities AS (
                SELECT DISTINCT credential_id FROM hf_credential_version
                WHERE credential_version_id = ANY(CAST(:versions AS bigint[]))
            ), occupants AS (
                SELECT v.credential_id, (j.upstream_state='6' OR j.orchestration_state='3') AS unknown
                FROM hf_creation_job j JOIN hf_credential_version v USING(credential_version_id)
                WHERE v.credential_id IN (SELECT credential_id FROM identities)
                AND NOT EXISTS (SELECT 1 FROM hf_provider_call c WHERE c.job_id=j.job_id
                    AND c.request_metadata->>'capacityReleasedAt' IS NOT NULL)
                AND (j.orchestration_state IN ('2','3','4') OR j.upstream_state IN ('1','2','6')
                    OR (j.orchestration_state IN ('0','1') AND j.lease_until>clock_timestamp()))
                UNION ALL
                SELECT v.credential_id, c.acceptance='unknown'
                FROM hf_provider_call c JOIN hf_credential_version v USING(credential_version_id)
                WHERE v.credential_id IN (SELECT credential_id FROM identities)
                AND c.operation='test' AND c.request_metadata->>'capacityReleasedAt' IS NULL
                AND (c.state='1' OR c.acceptance='unknown')
            )
            SELECT v.credential_version_id,
                count(o.credential_id)>=COALESCE((SELECT min(p.max_concurrency) FROM hf_routing_policy p
                    WHERE p.credential_id=v.credential_id AND p.enabled='Y'),1) AS full,
                COALESCE(bool_or(o.unknown),false) AS unknown
            FROM hf_credential_version v LEFT JOIN occupants o USING(credential_id)
            WHERE v.credential_version_id = ANY(CAST(:versions AS bigint[]))
            GROUP BY v.credential_version_id,v.credential_id
        '''), {'versions': list({row.credential_version_id for row in waiting})})
        reasons = {r.credential_version_id: ('capacity_unknown' if r.unknown else 'capacity_full')
                   for r in result if r.full}
        return {row.job_id: reasons[row.credential_version_id] for row in waiting
                if row.credential_version_id in reasons}

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

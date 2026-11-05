from sqlalchemy import select, func, or_, and_, not_
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.outbox_do import HfTaskEvent, HfOutboxEvent


class JobLeaseDao:
    @staticmethod
    async def has_execution_capacity(db, row, now):
        """同一凭据跨进程串行分配执行名额；等待任务本身不占名额。"""
        from module_higgsfield.entity.do.credential_do import HfCredentialVersion
        from module_higgsfield.entity.do.routing_do import HfRoutingPolicy
        identity = await db.scalar(select(HfCredentialVersion.credential_id).where(
            HfCredentialVersion.credential_version_id == row.credential_version_id))
        if identity is None:
            return False
        locked = await db.scalar(select(func.pg_try_advisory_xact_lock(
            func.hashtextextended(func.concat(func.current_schema(), ':generation-capacity:', str(identity)), 0))))
        if not locked:
            return False
        route = row.input_snapshot.get('route', {})
        policy = await db.scalar(select(HfRoutingPolicy).where(
            HfRoutingPolicy.policy_id == int(route.get('policyId', 0))))
        maximum = policy.max_concurrency if policy else route.get('maxConcurrency', 1)
        versions = select(HfCredentialVersion.credential_version_id).where(HfCredentialVersion.credential_id == identity)
        await db.flush()
        occupied = await db.scalar(select(func.count()).select_from(HfCreationJob).where(
            HfCreationJob.credential_version_id.in_(versions),
            HfCreationJob.job_id != row.job_id,
            or_(
                HfCreationJob.orchestration_state.in_(('2', '3', '4')),
                HfCreationJob.upstream_state.in_(('1', '2', '6')),
                and_(HfCreationJob.orchestration_state.in_(('0', '1')),
                     HfCreationJob.lease_until > now),
            ),
            not_(and_(HfCreationJob.kind == 'image', HfCreationJob.orchestration_state == '3',
                      HfCreationJob.next_action_time.is_(None), HfCreationJob.lease_owner.is_(None),
                      HfCreationJob.lease_until.is_(None))),
        ))
        return occupied < maximum

    @staticmethod
    async def now(db):
        return await db.scalar(select(func.clock_timestamp()))

    @staticmethod
    async def candidates(db, now, limit, kinds=None):
        # 依据持久领取事件轮转用户；跨进程共享，不依赖工作器内存。
        served = (select(HfCreationJob.actor_id.label('actor_id'),
                         func.max(HfTaskEvent.occurred_time).label('last_served'))
                  .join(HfTaskEvent, HfTaskEvent.job_id == HfCreationJob.job_id)
                  .where(HfTaskEvent.payload['stage'].astext == 'worker_claimed',
                         HfCreationJob.kind.in_(kinds) if kinds is not None else True)
                  .group_by(HfCreationJob.actor_id).subquery())
        eligible = (select(HfCreationJob.job_id.label('job_id'),
                           func.row_number().over(
                               partition_by=HfCreationJob.actor_id,
                               order_by=(HfCreationJob.next_action_time, HfCreationJob.job_id)
                           ).label('turn'))
                    .where(HfCreationJob.orchestration_state.in_(('0', '1', '2', '3', '4')),
                           HfCreationJob.next_action_time <= now,
                           or_(HfCreationJob.lease_until.is_(None), HfCreationJob.lease_until <= now),
                           HfCreationJob.kind.in_(kinds) if kinds is not None else True).subquery())
        return (
            await db.scalars(
                select(HfCreationJob)
                .join(eligible, eligible.c.job_id == HfCreationJob.job_id)
                .outerjoin(served, served.c.actor_id == HfCreationJob.actor_id)
                .where(
                    HfCreationJob.orchestration_state.in_(('0', '1', '2', '3', '4')),
                    HfCreationJob.next_action_time <= now,
                    or_(HfCreationJob.lease_until.is_(None), HfCreationJob.lease_until <= now),
                    HfCreationJob.kind.in_(kinds) if kinds is not None else True,
                )
                .order_by(eligible.c.turn, served.c.last_served.asc().nullsfirst(),
                          HfCreationJob.next_action_time, HfCreationJob.job_id)
                .limit(limit)
                .with_for_update(of=HfCreationJob, skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).all()

    @staticmethod
    async def lock_scheduler(db):
        # 仅串行化短领取事务，让后续领取看到最新服务时间，不锁网络请求。
        return await db.scalar(select(func.pg_try_advisory_xact_lock(
            func.hashtextextended(func.concat(func.current_schema(), ':generation-fair-scheduler'), 0))))

    @staticmethod
    async def owned(db, job_id, worker, token):
        return await db.scalar(
            select(HfCreationJob)
            .where(
                HfCreationJob.job_id == job_id,
                HfCreationJob.lease_owner == worker,
                HfCreationJob.fencing_token == token,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def recovery_event(db, row, now, worker):
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        db.add(
            HfTaskEvent(
                job_id=row.job_id,
                sequence=row.event_sequence,
                event_type='task.state',
                schema_version=1,
                payload={
                    'revision': str(row.revision),
                    'orchestrationState': 'submission_unknown',
                    'upstreamState': 'unknown',
                },
                occurred_time=now,
                **audit,
            )
        )
        db.add(
            HfOutboxEvent(
                event_type='task.changed',
                aggregate_type='creation_job',
                aggregate_id=row.job_id,
                payload={'jobId': str(row.job_id), 'sequence': str(row.event_sequence)},
                next_attempt_time=now,
                **audit,
            )
        )
        await db.flush()

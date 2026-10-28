from sqlalchemy import select, func, or_
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.outbox_do import HfTaskEvent, HfOutboxEvent


class JobLeaseDao:
    @staticmethod
    async def now(db):
        return await db.scalar(select(func.clock_timestamp()))

    @staticmethod
    async def candidates(db, now, limit, kinds=None):
        return (
            await db.scalars(
                select(HfCreationJob)
                .where(
                    HfCreationJob.orchestration_state.in_(('0', '1', '2', '3', '4')),
                    HfCreationJob.next_action_time <= now,
                    or_(HfCreationJob.lease_until.is_(None), HfCreationJob.lease_until <= now),
                    HfCreationJob.kind.in_(kinds) if kinds is not None else True,
                )
                .order_by(HfCreationJob.next_action_time, HfCreationJob.job_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
        ).all()

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

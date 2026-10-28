"""任务可见状态及通知在同一事务中持久化。"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.outbox_do import HfOutboxEvent, HfTaskEvent


class JobEventDao:
    ORCHESTRATION = ('accepted', 'preparing', 'submitting', 'submission_unknown', 'running', 'finished', 'blocked')
    UPSTREAM = ('not_submitted', 'queued', 'running', 'succeeded', 'failed', 'cancelled', 'unknown')

    @staticmethod
    async def usage(db, job, now, worker, usage_state):
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        db.add(
            HfTaskEvent(
                job_id=job.job_id,
                sequence=job.event_sequence,
                event_type='usage.updated',
                schema_version=1,
                payload={'usageState': usage_state, 'billingVisibility': 'unavailable'},
                occurred_time=now,
                **audit,
            )
        )
        db.add(
            HfOutboxEvent(
                event_type='task.changed',
                aggregate_type='creation_job',
                aggregate_id=job.job_id,
                payload={'jobId': str(job.job_id), 'sequence': str(job.event_sequence)},
                next_attempt_time=now,
                **audit,
            )
        )
        await db.flush()

    @staticmethod
    async def output(db, job, output, now, worker):
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        db.add(
            HfTaskEvent(
                job_id=job.job_id,
                sequence=job.event_sequence,
                event_type='output.state',
                schema_version=1,
                payload={
                    'outputId': str(output.output_id),
                    'revision': str(output.revision),
                    'archiveState': (
                        'not_started',
                        'archiving',
                        'archived',
                        'archive_failed',
                        'source_expired',
                        'not_applicable',
                    )[int(output.archive_state)],
                },
                occurred_time=now,
                **audit,
            )
        )
        db.add(
            HfOutboxEvent(
                event_type='task.changed',
                aggregate_type='creation_job',
                aggregate_id=job.job_id,
                payload={'jobId': str(job.job_id), 'sequence': str(job.event_sequence)},
                next_attempt_time=now,
                **audit,
            )
        )
        await db.flush()

    @classmethod
    async def state(cls, db: AsyncSession, row: HfCreationJob, now: datetime, worker: str) -> None:
        audit = {'create_by': worker, 'update_by': worker, 'create_time': now, 'update_time': now}
        db.add(
            HfTaskEvent(
                job_id=row.job_id,
                sequence=row.event_sequence,
                event_type='task.state',
                schema_version=1,
                payload={
                    'revision': str(row.revision),
                    'orchestrationState': cls.ORCHESTRATION[int(row.orchestration_state)],
                    'upstreamState': cls.UPSTREAM[int(row.upstream_state)],
                    'cancelState': ('none', 'requested', 'confirmed', 'rejected', 'unsupported')[int(row.cancel_state)],
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

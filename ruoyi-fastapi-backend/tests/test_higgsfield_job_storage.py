"""任务与消息表真实迁移、去重及事务回滚验证。"""

import importlib.util
import os
from pathlib import Path
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.outbox_do import HfTaskEvent, HfOutboxEvent, HfProcessedEvent
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class JobStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'job_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_29_jobs_outbox.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def migrate(self, operation):
        async with self.engine.begin() as conn:

            def execute(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    getattr(self.migration, operation)()

            await conn.run_sync(execute)

    def job(self, **changes):
        return HfCreationJob(
            **(
                dict(
                    project_id=1,
                    actor_id=1,
                    department_snapshot={},
                    kind='image',
                    idempotency_key='request',
                    request_hash='a' * 64,
                    model_version_id=1,
                    model_variant_id=1,
                    credential_version_id=1,
                    platform_price_version_id=1,
                    input_snapshot={'schemaVersion': 1},
                    **WriteService.audit(self.owner),
                )
                | changes
            )
        )

    async def test_permanent_request_dedup_and_state_constraints(self):
        async with self.sessions() as db:
            db.add(self.job())
            await db.flush()
            for changes in (
                {},
                {'idempotency_key': 'chat', 'kind': 'chat'},
                {'idempotency_key': 'image', 'chat_session_id': 1},
                {'idempotency_key': 'lease', 'lease_owner': 'worker'},
                {'idempotency_key': 'state', 'orchestration_state': '9'},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(self.job(**changes))
                        await db.flush()
            db.add(self.job(idempotency_key='valid_chat', kind='chat', chat_session_id=1, context_session_revision=1))
            await db.flush()

    async def test_event_dedup_and_atomic_business_message_rollback(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            job = self.job()
            db.add(job)
            await db.flush()
            db.add(
                HfTaskEvent(
                    job_id=job.job_id,
                    sequence=1,
                    event_type='task.state',
                    payload={'state': 'accepted'},
                    occurred_time=audit['create_time'],
                    **audit,
                )
            )
            event = HfOutboxEvent(
                event_type='job.accepted',
                aggregate_type='creation_job',
                aggregate_id=job.job_id,
                payload={'jobId': str(job.job_id)},
                next_attempt_time=audit['create_time'],
                **audit,
            )
            db.add(event)
            await db.flush()
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        HfTaskEvent(
                            job_id=job.job_id,
                            sequence=1,
                            event_type='task.state',
                            payload={},
                            occurred_time=audit['create_time'],
                            **audit,
                        )
                    )
                    await db.flush()
            db.add(
                HfProcessedEvent(
                    consumer_name='test', event_id=event.event_id, processed_time=audit['create_time'], **audit
                )
            )
            await db.flush()
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    db.add(
                        HfProcessedEvent(
                            consumer_name='test', event_id=event.event_id, processed_time=audit['create_time'], **audit
                        )
                    )
                    await db.flush()
            await db.rollback()
            for table in ('hf_creation_job', 'hf_task_event', 'hf_outbox_event', 'hf_processed_event'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM ' + table)), 0)

    async def test_comments_and_migration_roundtrip(self):
        async with self.sessions() as db:
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_creation_job','hf_job_reference','hf_task_event','hf_outbox_event','hf_processed_event') AND a.attnum>0 AND NOT a.attisdropped AND col_description(c.oid,a.attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            count = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_creation_job','hf_job_reference','hf_task_event','hf_outbox_event','hf_processed_event') AND x.contype='f'"
                )
            )
            self.assertEqual(count, 0)
        await self.migrate('downgrade')
        await self.migrate('upgrade')

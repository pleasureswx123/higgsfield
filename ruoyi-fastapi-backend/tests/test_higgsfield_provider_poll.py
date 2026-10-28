"""真实查询事务与合成供应商响应，不发送外部网络请求。"""

import os
import importlib.util
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.provider_poll_service import ProviderPollService
from module_higgsfield.service.provider_submission_result_service import ProviderSubmissionResultService
from tests import test_higgsfield_provider_synchronous_result as sync
from tests.test_higgsfield_output_discovery import crypto


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderPollTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = sync.SynchronousResultTests.cleanup_schema
    migrate = sync.SynchronousResultTests.migrate
    job = sync.SynchronousResultTests.job

    async def asyncSetUp(self) -> None:
        await sync.SynchronousResultTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'poll_usage', sync.submission.intent.pipeline.MIGRATIONS / '20261027_38_usage_records.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET kind='video'"))
            await db.execute(text("UPDATE hf_provider_call SET operation='video_submit'"))
            await db.commit()
            await ProviderSubmissionResultService.record(
                db,
                self.lease,
                self.call_id,
                ProviderSubmissionResult(
                    acceptance='accepted',
                    transport='response',
                    httpStatus=200,
                    upstreamTaskId='video-task',
                ),
            )
        await self.claim()

    async def claim(self) -> None:
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
            self.lease = (await JobLeaseService.claim(db, 'poll-test'))[0]

    async def test_success_outputs_usage_and_call_commit_together(self) -> None:
        async with self.sessions() as db:
            identity = await ProviderPollService.begin(db, self.lease, 'b' * 64)
            with self.assertRaises(ServiceWarning):
                await ProviderPollService.begin(db, self.lease, 'b' * 64)
            await ProviderPollService.record(
                db,
                self.lease,
                identity,
                http_status=200,
                body={
                    'id': 'video-task',
                    'status': 'succeeded',
                    'content': {'video_url': 'https://example.com/video?key=secret'},
                    'usage': {'completion_tokens': 368100},
                },
                crypto=crypto(),
            )
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '5')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
            metadata = await db.scalar(
                text('SELECT response_metadata FROM hf_provider_call WHERE call_id=:id'), {'id': identity}
            )
            self.assertEqual(metadata['usage']['completionTokens'], '368100')
            self.assertEqual(await db.scalar(text('SELECT video_tokens FROM hf_usage_record')), 368100)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertNotIn('secret', str(metadata))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_missing_output_then_timeout_preserves_success(self) -> None:
        async with self.sessions() as db:
            identity = await ProviderPollService.begin(db, self.lease, 'b' * 64)
            await ProviderPollService.record(
                db,
                self.lease,
                identity,
                http_status=200,
                body={
                    'id': 'video-task',
                    'status': 'succeeded',
                },
            )
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '4')
            self.assertEqual(await db.scalar(text('SELECT upstream_state FROM hf_creation_job')), '3')
        await self.claim()
        async with self.sessions() as db:
            identity = await ProviderPollService.begin(db, self.lease, 'b' * 64)
            await ProviderPollService.record(db, self.lease, identity, transport='timeout')
            self.assertEqual(await db.scalar(text('SELECT upstream_state FROM hf_creation_job')), '3')
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE operation='video_submit'")), 1
            )

    async def test_event_failure_rolls_back_call_outputs_and_job(self) -> None:
        async with self.sessions() as db:
            identity = await ProviderPollService.begin(db, self.lease, 'b' * 64)
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))),
                self.assertRaises(RuntimeError),
            ):
                await ProviderPollService.record(
                    db,
                    self.lease,
                    identity,
                    http_status=200,
                    body={
                        'id': 'video-task',
                        'status': 'completed',
                        'content': {'video_url': 'https://example.com/video'},
                    },
                    crypto=crypto(),
                )
            self.assertEqual(
                await db.scalar(text('SELECT state FROM hf_provider_call WHERE call_id=:id'), {'id': identity}), '1'
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 0)
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '4')

    async def test_repeated_poll_usage_deduplicates_and_new_revision_changes_task(self):
        revisions = []
        for count in (100, 100, 120):
            async with self.sessions() as db:
                identity = await ProviderPollService.begin(db, self.lease, 'b' * 64)
                await ProviderPollService.record(
                    db,
                    self.lease,
                    identity,
                    http_status=200,
                    body={'id': 'video-task', 'status': 'succeeded', 'usage': {'completion_tokens': count}},
                )
                revisions.append(await db.scalar(text('SELECT revision FROM hf_creation_job')))
            await self.claim()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 2)
            rows = (
                await db.execute(text('SELECT revision_no,video_tokens FROM hf_usage_record ORDER BY revision_no'))
            ).all()
            self.assertEqual(rows, [(1, 100), (2, 120)])
            self.assertEqual(revisions[0], revisions[1])
            self.assertGreater(revisions[2], revisions[1])

    async def test_paused_and_archived_project_keeps_accepted_video_polling(self):
        from uuid import uuid4
        from module_higgsfield.service.project_lifecycle_service import ProjectLifecycleService
        from module_higgsfield.entity.vo.project_vo import ProjectPause, ProjectArchive
        for filename in ('20261028_74_project_lifecycle.py', '20261028_75_project_manage.py'):
            spec = importlib.util.spec_from_file_location('poll_lifecycle', sync.submission.intent.pipeline.MIGRATIONS / filename)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        for action, model in (('pause', ProjectPause), ('archive', ProjectArchive)):
            async with self.sessions() as db:
                job = (await db.execute(text('SELECT project_id,credential_version_id,upstream_task_id FROM hf_creation_job'))).one()
                revision = await db.scalar(text('SELECT revision FROM hf_project WHERE project_id=:id'), {'id': job.project_id})
                await ProjectLifecycleService.change(db, self.owner, job.project_id, action,
                    model(revision=str(revision), reason='在途任务治理核验'), str(uuid4()))
                call = await ProviderPollService.begin(db, self.lease, 'c' * 64)
                await ProviderPollService.record(db, self.lease, call, http_status=200,
                    body={'id': 'video-task', 'status': 'running'})
                current = (await db.execute(text('SELECT project_id,credential_version_id,upstream_task_id FROM hf_creation_job'))).one()
                self.assertEqual(current, job)
                self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE operation='video_submit'")), 1)
                self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '4')
            await self.claim()

    async def test_actor_revocation_does_not_cancel_accepted_video_tracking(self):
        async with self.sessions() as db:
            original = (await db.execute(text('SELECT actor_id,project_id,credential_version_id,upstream_task_id FROM hf_creation_job'))).one()
            await db.execute(text("UPDATE sys_user SET status='1' WHERE user_id=:actor"), {'actor': original.actor_id})
            await db.execute(text("UPDATE hf_project_member SET status='1' WHERE user_id=:actor AND project_id=:project"),
                {'actor': original.actor_id, 'project': original.project_id})
            await db.execute(text('DELETE FROM sys_user_role WHERE user_id=:actor'), {'actor': original.actor_id})
            await db.commit()
            identity = await ProviderPollService.begin(db, self.lease, 'd' * 64)
            await ProviderPollService.record(db, self.lease, identity, http_status=200,
                body={'id': 'video-task', 'status': 'running'})
            self.assertEqual((await db.execute(text('SELECT actor_id,project_id,credential_version_id,upstream_task_id FROM hf_creation_job'))).one(), original)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE operation='video_submit'")), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE operation='video_poll'")), 1)

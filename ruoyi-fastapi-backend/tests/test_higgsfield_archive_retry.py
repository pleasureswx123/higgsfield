"""归档重试的真实事务、幂等与输出范围。"""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import unittest
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.generation_action_vo import GenerationRetryArchive
from module_higgsfield.service.generation_archive_retry_service import GenerationArchiveRetryService
from tests.test_higgsfield_output_archive import OutputArchiveTests
from tests.test_higgsfield_projects import ProjectDatabaseTests

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ArchiveRetryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = OutputArchiveTests.cleanup_schema
    migrate = OutputArchiveTests.migrate
    output = OutputArchiveTests.output
    job = OutputArchiveTests.job

    async def asyncSetUp(self):
        await OutputArchiveTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('retry_permission', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_47_archive_retry_permission.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_16_audit.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        created, _ = await ProjectDatabaseTests.create(self)
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_creation_job SET project_id=:id'), {'id': int(created['data']['id'])})
            self.job_id = await db.scalar(text('SELECT job_id FROM hf_generated_output WHERE output_id=:id'), {'id': self.identity})
            await db.execute(text("UPDATE hf_generated_output SET archive_state='3',next_retry_time=clock_timestamp()+interval '1 hour'"))
            await db.commit()

    async def retry(self, ids=None, key=None, revision='1', user=None):
        async with self.sessions() as db:
            return await GenerationArchiveRetryService.retry(db, user or self.owner, self.job_id, GenerationRetryArchive(revision=revision, outputIds=ids), key or str(uuid4()))

    async def test_retry_and_replay_do_not_regenerate(self):
        key = str(uuid4())
        first, replayed = await self.retry(key=key)
        self.assertFalse(replayed)
        again, replayed = await self.retry(key=key)
        self.assertTrue(replayed)
        self.assertEqual(first['data'], again['data'])
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT archive_state,revision FROM hf_generated_output'))).one()
            self.assertEqual(tuple(row), ('0', 2))
            row = (await db.execute(text('SELECT orchestration_state,upstream_state,revision FROM hf_creation_job'))).one()
            self.assertEqual(tuple(row), ('5', '3', 2))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)

    async def test_wrong_output_and_expired_source_leave_state_unchanged(self):
        with self.assertRaises(ServiceWarning):
            await self.retry(ids=[str(self.identity), '999999'])
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET source_expires_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.retry()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)

    async def test_nonmember_cannot_retry_or_replay(self):
        key = str(uuid4())
        await self.retry(key=key)
        with self.assertRaises(ServiceWarning):
            await self.retry(key=key, user=self.other)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

    async def test_manual_retry_is_consumed_by_archive_worker(self):
        worker, downloader = await OutputArchiveTests.archive_worker(self)
        self.assertEqual(await worker.run_once(), [])
        await self.retry(ids=[str(self.identity)])
        results = await worker.run_once()
        self.assertEqual(results[0]['status'], 'archived')
        downloader.download.assert_awaited_once_with('https://media.example/result.png', kind='image')
        self.assertEqual(await worker.run_once(), [])
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT archive_state,file_id FROM hf_generated_output'))).one()
            self.assertEqual(row.archive_state, '2')
            self.assertIsNotNone(row.file_id)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT upstream_state FROM hf_creation_job')), '3')
            sequences = (await db.execute(text('SELECT sequence FROM hf_task_event ORDER BY sequence'))).scalars().all()
            self.assertEqual(sequences, [1, 2, 3])
            self.assertEqual(await db.scalar(text('SELECT event_sequence FROM hf_creation_job')), 3)

    async def test_event_failure_rolls_back_all_retry_facts(self):
        from unittest.mock import AsyncMock, patch
        from module_higgsfield.dao.job_event_dao import JobEventDao
        key = str(uuid4())
        with patch.object(JobEventDao, 'output', AsyncMock(side_effect=RuntimeError('事件持久化失败'))):
            with self.assertRaises(RuntimeError):
                await self.retry(key=key)
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT archive_state,revision FROM hf_generated_output'))).one()
            self.assertEqual(tuple(row), ('3', 1))
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)
        _, replayed = await self.retry(key=key)
        self.assertFalse(replayed)

    async def test_competing_retry_requests_accept_only_one_revision(self):
        import asyncio
        results = await asyncio.gather(self.retry(), self.retry(), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, tuple) for result in results), 1)
        self.assertEqual(sum(isinstance(result, ServiceWarning) for result in results), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)

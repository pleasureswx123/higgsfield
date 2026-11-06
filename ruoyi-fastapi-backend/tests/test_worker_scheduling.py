"""通知、公平领取与安全停机回归，不调用真实供应商。"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import text
from module_higgsfield.service.bounded_dispatch_service import serve_bounded
from module_higgsfield.service.worker_control_service import serve_controlled
from module_higgsfield.service.worker_wakeup_service import worker_notifications
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.dao.job_event_dao import JobEventDao
from tests.test_higgsfield_job_leases import JobLeaseTests


class SchedulingTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_file_failure_preserves_execution_and_recovers(self):
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def execute(self, *_): pass

        # 分别覆盖临时文件写入失败、Windows 替换目标文件被占用。
        for operation in ('write_text', 'replace'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                stop, failed, recovered = (asyncio.Event() for _ in range(3))
                completed = []
                original = getattr(Path, operation)
                calls = 0

                def write(path, *args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        failed.set()
                        raise PermissionError('模拟文件被占用')
                    result = original(path, *args, **kwargs)
                    recovered.set()
                    return result

                async def serve(event):
                    await failed.wait()
                    await recovered.wait()
                    completed.append(True)
                    event.set()

                with patch.object(Path, operation, new=write):
                    await asyncio.wait_for(serve_controlled(SimpleNamespace(serve=serve),
                        SimpleNamespace(connect=Connection), stop, control_dir=directory), 4)
                self.assertEqual(completed, [True])
                self.assertEqual(json.loads(Path(directory, 'status.json').read_text())['state'], 'stopped')

    async def test_final_heartbeat_failure_does_not_mask_worker_error(self):
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def execute(self, *_): pass

        async def serve(event):
            raise ValueError('模拟业务异常')

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(Path, 'replace', side_effect=PermissionError('模拟文件被占用')):
            with self.assertRaisesRegex(ValueError, '模拟业务异常'):
                await serve_controlled(SimpleNamespace(serve=serve), SimpleNamespace(connect=Connection),
                    asyncio.Event(), control_dir=directory)

    async def test_claim_connection_failure_preserves_running_task_and_recovers(self):
        from sqlalchemy.exc import OperationalError
        stop, entered, recovered = (asyncio.Event() for _ in range(3))
        calls = 0
        completed = []

        async def claim(limit):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [1]
            if calls == 2:
                raise OperationalError('query', {}, OSError('连接中断'))
            return [2]

        async def execute(item):
            if item == 1:
                entered.set()
                await recovered.wait()
            else:
                recovered.set()
                stop.set()
            completed.append(item)

        task = asyncio.create_task(serve_bounded(stop, 2, claim, execute, poll_seconds=0.01))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.wait_for(task, 3)
            self.assertEqual(sorted(completed), [1, 2])
            self.assertEqual(calls, 3)
        finally:
            stop.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_notification_wakes_idle_without_waiting_for_scan(self):
        stop, wake, queried, handled = (asyncio.Event() for _ in range(4))
        queue = []

        async def claim(limit):
            queried.set()
            result, queue[:] = queue[:limit], queue[limit:]
            return result

        async def execute(item):
            handled.set()

        task = asyncio.create_task(serve_bounded(stop, 2, claim, execute, wakeup=wake, poll_seconds=30))
        try:
            await asyncio.wait_for(queried.wait(), 1)
            queue.append(1)
            wake.set()
            await asyncio.wait_for(handled.wait(), 0.5)
        finally:
            stop.set()
            await asyncio.wait_for(task, 1)

    async def test_missing_notification_is_recovered_by_scan(self):
        stop, queried, handled = (asyncio.Event() for _ in range(3))
        queue = []

        async def claim(limit):
            queried.set()
            result, queue[:] = queue[:limit], queue[limit:]
            return result

        async def execute(item):
            handled.set()

        task = asyncio.create_task(serve_bounded(stop, 1, claim, execute, poll_seconds=0.05))
        try:
            await queried.wait()
            queue.append(1)
            await asyncio.wait_for(handled.wait(), 1)
        finally:
            stop.set()
            await task

    async def test_stop_does_not_claim_more_and_drains_inflight(self):
        stop, started, release = (asyncio.Event() for _ in range(3))
        claim = AsyncMock(return_value=[1])

        async def execute(item):
            started.set()
            await release.wait()

        task = asyncio.create_task(serve_bounded(stop, 1, claim, execute))
        await started.wait()
        stop.set()
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        release.set()
        await task
        self.assertEqual(claim.await_count, 1)

    async def test_control_file_stops_worker_and_reports_final_state(self):
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def execute(self, *_): pass

        with tempfile.TemporaryDirectory() as directory:
            stop = asyncio.Event()
            async def serve(event):
                await event.wait()

            worker = SimpleNamespace(serve=serve)
            engine = SimpleNamespace(connect=Connection)
            Path(directory, 'stop').touch()
            await asyncio.wait_for(serve_controlled(worker, engine, stop,
                control_dir=directory, mode='image', concurrency=2, drain_seconds=1), 3)
            status = json.loads(Path(directory, 'status.json').read_text())
            self.assertEqual(status['state'], 'stopped')
            self.assertEqual(status['concurrency'], 2)

    async def test_drain_deadline_cancels_inflight_and_records_timeout(self):
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass
            async def execute(self, *_): pass

        cancelled = asyncio.Event()

        async def serve(event):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with tempfile.TemporaryDirectory() as directory:
            stop = asyncio.Event()
            stop.set()
            with self.assertRaises(RuntimeError):
                await serve_controlled(SimpleNamespace(serve=serve), SimpleNamespace(connect=Connection), stop,
                    control_dir=directory, drain_seconds=0.02)
            self.assertTrue(cancelled.is_set())
            self.assertEqual(json.loads(Path(directory, 'status.json').read_text())['state'], 'drain_timeout')

    async def test_recovery_serve_uses_image_evidence_candidates(self):
        from module_higgsfield.service.image_archive_recovery_worker import ImageArchiveRecoveryWorker
        stop = asyncio.Event()
        worker = ImageArchiveRecoveryWorker.__new__(ImageArchiveRecoveryWorker)
        worker.batch_size = 1

        class Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *_): pass

        worker.sessions = Session

        async def process(identity, revision):
            self.assertEqual((identity, revision), (7, 2))
            stop.set()

        worker.process = process
        with patch('module_higgsfield.dao.job_lease_dao.JobLeaseDao.now', new=AsyncMock()), \
             patch('module_higgsfield.dao.provider_response_dao.ProviderResponseDao.recovery_candidates',
                   new=AsyncMock(return_value=[(7, 2)])) as recovery, \
             patch('module_higgsfield.dao.generated_output_dao.GeneratedOutputDao.archive_candidates',
                   new=AsyncMock()) as ordinary:
            await asyncio.wait_for(worker.serve(stop), 1)
            recovery.assert_awaited_once()
            ordinary.assert_not_awaited()


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class FairSchedulingTests(JobLeaseTests):
    async def test_scheduler_lock_is_scoped_to_schema(self):
        from module_higgsfield.dao.job_lease_dao import JobLeaseDao
        async with self.sessions() as first, self.sessions() as second:
            self.assertTrue(await JobLeaseDao.lock_scheduler(first))
            self.assertFalse(await JobLeaseDao.lock_scheduler(second))
            await second.rollback()
            # 切换到独立命名空间，不创建或改动任何业务数据。
            await second.execute(text('SET LOCAL search_path TO pg_catalog'))
            self.assertTrue(await JobLeaseDao.lock_scheduler(second))
            await first.rollback()
            await second.rollback()
            self.assertTrue(await JobLeaseDao.lock_scheduler(second))

    async def test_listener_reconnects_and_rescans(self):
        stop = asyncio.Event()
        connections = []
        engine = self.engine

        class Connection:
            async def __aenter__(self):
                self.connection = await engine.connect()
                connections.append((await self.connection.get_raw_connection()).driver_connection)
                return self.connection

            async def __aexit__(self, *_):
                await self.connection.close()

        async with worker_notifications(SimpleNamespace(connect=Connection), stop) as wake:
            await asyncio.wait_for(wake.wait(), 3)
            wake.clear()
            await connections[0].close()
            await asyncio.wait_for(wake.wait(), 10)
            self.assertGreaterEqual(len(connections), 2)
            stop.set()

    async def test_two_users_alternate_across_workers_and_fill_unused_slots(self):
        for actor in (1, 2):
            for index in range(6):
                await self.seed(actor_id=actor, idempotency_key=f'{actor}-{index}')
        actors = []
        for index in range(12):
            lease = (await self.claim(f'worker-{index}'))[0]
            async with self.sessions() as db:
                actors.append(await db.scalar(text('SELECT actor_id FROM hf_creation_job WHERE job_id=:id'), {'id': lease.job_id}))
        self.assertEqual(actors, [1, 2] * 6)

    async def test_batch_interleaves_users(self):
        for actor in (1, 2):
            for index in range(4):
                await self.seed(actor_id=actor, idempotency_key=f'{actor}-{index}')
        async with self.sessions() as db:
            leases = await JobLeaseService.claim(db, 'batch', limit=4)
        actors = []
        async with self.sessions() as db:
            for lease in leases:
                actors.append(await db.scalar(text('SELECT actor_id FROM hf_creation_job WHERE job_id=:id'), {'id': lease.job_id}))
        self.assertEqual(actors, [1, 2, 1, 2])

    async def test_saturated_account_does_not_block_other_user(self):
        first = await self.seed(actor_id=1, idempotency_key='busy')
        second = await self.seed(actor_id=2, idempotency_key='free')

        async def capacity(db, row, now):
            return row.job_id != first

        with patch('module_higgsfield.dao.job_lease_dao.JobLeaseDao.has_execution_capacity', side_effect=capacity):
            self.assertEqual((await self.claim('free-worker'))[0].job_id, second)

    async def test_notify_only_after_commit_and_not_after_rollback(self):
        stop = asyncio.Event()
        async with worker_notifications(self.engine, stop) as wake:
            await asyncio.wait_for(wake.wait(), 3)
            wake.clear()
            async with self.sessions() as db:
                row = self.job(event_sequence=1, idempotency_key='rollback')
                db.add(row)
                await db.flush()
                await JobEventDao.state(db, row, await db.scalar(text('SELECT clock_timestamp()')), 'test')
                await asyncio.sleep(0.05)
                self.assertFalse(wake.is_set())
                await db.rollback()
            await asyncio.sleep(0.05)
            self.assertFalse(wake.is_set())
            async with self.sessions() as db:
                row = self.job(event_sequence=1, idempotency_key='commit')
                db.add(row)
                await db.flush()
                await JobEventDao.state(db, row, await db.scalar(text('SELECT clock_timestamp()')), 'test')
                await db.commit()
            await asyncio.wait_for(wake.wait(), 1)
            stop.set()

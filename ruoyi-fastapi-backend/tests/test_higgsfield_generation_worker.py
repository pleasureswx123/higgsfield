"""调度器真实租约续期与未知提交恢复，不使用真实供应商。"""

import asyncio
import os
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.preparation_diagnostic_service import PreparationDiagnosticService
from module_higgsfield.dao.generation_read_dao import GenerationReadDao

from sqlalchemy import text

from module_higgsfield.service.generation_worker_service import GenerationWorkerService, JobExecutionContext
from module_higgsfield.service.job_lease_service import JobLeaseService
from tests import test_higgsfield_job_leases as leases


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationWorkerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = leases.JobLeaseTests.cleanup_schema
    migrate = leases.JobLeaseTests.migrate
    job = leases.JobLeaseTests.job
    seed = leases.JobLeaseTests.seed
    async def asyncSetUp(self):
        await leases.JobLeaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('worker_audit', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_16_audit.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_preparation_failure_is_atomic_deduplicated_and_not_reused_after_submission(self):
        identity = await self.seed()

        async def prepare(context):
            async with context.sessions() as db:
                job, _ = await JobLeaseService.guard(db, context.lease)
                initial = job.orchestration_state == '0'
            if initial:
                await context.advance('prepare')
            raise ServiceWarning(message='secret-provider-key', data={'errorCode': 'PROVIDER_CREDENTIAL_UNAVAILABLE'})

        worker = GenerationWorkerService(self.sessions, 'test-worker', {'prepare': prepare})
        for _ in range(2):
            self.assertEqual((await worker.run_once())[0]['status'], 'handler_failed')
            async with self.sessions() as db:
                row = await GenerationReadDao.job(db, identity)
                diagnostic = await PreparationDiagnosticService.read(db, row)
                self.assertEqual(diagnostic['code'], 'PROVIDER_CREDENTIAL_UNAVAILABLE')
                self.assertEqual(row.orchestration_state, '1')
                self.assertIsNone(row.lease_owner)
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
                self.assertNotIn('secret-provider-key', str((await db.execute(text('SELECT before_after,reason FROM hf_audit_log'))).all()))
                await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
                await db.commit()
        async def recovered(context):
            await context.advance('submit')
        worker.handlers['prepare'] = recovered
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            row = await GenerationReadDao.job(db, identity)
            self.assertIsNone(await PreparationDiagnosticService.read(db, row))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

    async def test_unavailable_handler_defers_without_state_change(self) -> None:
        await self.seed()
        worker = GenerationWorkerService(self.sessions, 'test-worker', {})
        result = await worker.run_once()
        self.assertEqual(result[0]['status'], 'handler_unavailable')
        async with self.sessions() as db:
            row = (
                await db.execute(text('SELECT orchestration_state,lease_owner,event_sequence FROM hf_creation_job'))
            ).one()
            self.assertEqual(tuple(row), ('0', None, 0))

    async def test_diagnostic_failure_rolls_back_release_and_revision(self):
        identity = await self.seed(orchestration_state='1')
        async with self.sessions() as db:
            lease = (await JobLeaseService.claim(db, 'test-worker'))[0]
        with patch(
            'module_higgsfield.service.preparation_diagnostic_service.PreparationDiagnosticDao.add',
            AsyncMock(side_effect=RuntimeError('测试审计写入失败')),
        ):
            async with self.sessions() as db:
                with self.assertRaises(RuntimeError):
                    await JobLeaseService.release(db, lease, retry_after_seconds=30, diagnostic_code='PREPARATION_FAILED')
        async with self.sessions() as db:
            row = await GenerationReadDao.job(db, identity)
            self.assertEqual(row.revision, lease.revision)
            self.assertEqual(row.lease_owner, 'test-worker')
            self.assertEqual(row.event_sequence, 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 0)

    async def test_failed_submit_recovers_only_into_reconciliation(self) -> None:
        await self.seed()
        calls = []

        async def prepare(context: JobExecutionContext) -> None:
            calls.append('prepare')
            await context.advance('prepare')
            await context.advance('submit')
            raise RuntimeError('模拟外部调用响应丢失，错误正文不得进入任务结果')

        async def reconcile(context: JobExecutionContext) -> None:
            calls.append('reconcile')
            await context.advance('accepted', upstream_task_id='verified-upstream-id')

        worker = GenerationWorkerService(
            self.sessions, 'test-worker', {'prepare': prepare, 'reconcile_submission': reconcile}
        )
        self.assertEqual((await worker.run_once())[0]['status'], 'handler_failed')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        self.assertEqual(calls, ['prepare', 'reconcile'])
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT orchestration_state,upstream_task_id FROM hf_creation_job'))).one()
            self.assertEqual(tuple(row), ('4', 'verified-upstream-id'))

    async def test_renewal_uses_updated_revision_and_prevents_takeover(self) -> None:
        await self.seed()
        entered = asyncio.Event()

        async def prepare(context: JobExecutionContext) -> None:
            await context.advance('prepare')
            entered.set()
            await asyncio.sleep(6)

        worker = GenerationWorkerService(
            self.sessions, 'test-worker', {'prepare': prepare}, lease_seconds=5, handler_timeout=15
        )
        task = asyncio.create_task(worker.run_once())
        try:
            await entered.wait()
            await asyncio.sleep(5.2)
            async with self.sessions() as db:
                self.assertEqual(await JobLeaseService.claim(db, 'competing-worker'), [])
            self.assertEqual((await task)[0]['status'], 'handled')
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

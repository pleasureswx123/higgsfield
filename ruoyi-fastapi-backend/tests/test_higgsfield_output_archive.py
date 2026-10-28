"""归档阶段并发、文件绑定及事件回滚。"""

import importlib.util
import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.output_archive_service import OutputArchiveService
from module_higgsfield.service.output_archive_worker import OutputArchiveWorker
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_generated_outputs as outputs
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class OutputArchiveTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = outputs.GeneratedOutputTests.cleanup_schema
    migrate = outputs.GeneratedOutputTests.migrate
    output = outputs.GeneratedOutputTests.output
    job = storage.JobStorageTests.job

    async def asyncSetUp(self):
        await outputs.GeneratedOutputTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'archive_files', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_06_assets.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            job = self.job(orchestration_state='5', upstream_state='3', billing_state='0')
            db.add(job)
            await db.flush()
            output = self.output(job_id=job.job_id, source_url_ciphertext=b'encrypted-test-source')
            file = HfStoredFile(
                storage_key='test/archive',
                sha256='a' * 64,
                byte_size=64,
                mime_type='image/png',
                state='1',
                **WriteService.audit(self.owner),
            )
            db.add_all([output, file])
            await db.flush()
            self.identity, self.file_id = output.output_id, file.file_id
            await db.commit()

    async def change(self, revision, action, **kwargs):
        async with self.sessions() as db:
            db.autoflush = False
            return await OutputArchiveService.mutate(
                db, self.identity, revision=revision, action=action, worker='archiver', **kwargs
            )

    async def archive_worker(self):
        crypto = OutputSourceCryptoService(CredentialKeyring('v1', {'v1': b'x' * 32}, b'y' * 32))
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, self.identity)
            output.source_url_ciphertext = crypto.encrypt(
                'https://media.example/result.png', output.job_id, output.ordinal
            )
            await db.commit()
        downloader = AsyncMock()
        downloader.download.return_value = dict(
            storage_key='media/' + 'c' * 32,
            sha256='d' * 64,
            byte_size=72,
            mime_type='image/png',
            width=16,
            height=8,
        )
        return OutputArchiveWorker(self.sessions, 'archive-worker', downloader, crypto), downloader

    async def test_worker_competition_downloads_once(self):
        worker, downloader = await self.archive_worker()
        results = await asyncio.gather(worker.process(self.identity, 1), worker.process(self.identity, 1))
        self.assertEqual(sorted(row['status'] for row in results), ['archived', 'skipped'])
        downloader.download.assert_awaited_once_with('https://media.example/result.png', kind='image')
        self.assertEqual(await worker.run_once(), [])
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, self.identity)
            self.assertEqual(output.archive_state, '2')
            self.assertIsNotNone(output.file_id)

    async def test_worker_failure_delays_retry_and_recovers_expired_lease(self):
        worker, downloader = await self.archive_worker()
        downloader.download.side_effect = ValueError('模拟无效媒体')
        self.assertEqual((await worker.run_once())[0]['status'], 'failed')
        self.assertEqual(await worker.run_once(), [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
            await db.execute(
                text(
                    "UPDATE hf_generated_output SET archive_state='1', next_retry_time=clock_timestamp()-interval '1 second'"
                )
            )
            await db.commit()
        downloader.download.side_effect = None
        self.assertEqual((await worker.run_once())[0]['status'], 'archived')

    async def test_download_registration_is_atomic_and_replayable(self):
        await self.change(1, 'begin')
        facts = dict(
            storage_key='media/' + 'b' * 32, sha256='c' * 64, byte_size=72, mime_type='image/png', width=16, height=8
        )

        async def register(revision=2):
            async with self.sessions() as db:
                return await OutputArchiveService.register_download(
                    db, self.identity, revision=revision, worker='archiver', facts=facts
                )

        original = JobEventDao.output

        async def fail(*args):
            await original(*args)
            raise RuntimeError('模拟事件失败')

        with patch.object(JobEventDao, 'output', side_effect=fail), self.assertRaises(RuntimeError):
            await register()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '1')
        result = await register()
        self.assertEqual(result['archiveState'], 'archived')
        self.assertEqual(await register(), result)
        facts['storage_key'] = 'media/' + 'd' * 32
        with self.assertRaises(ServiceWarning):
            await register()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 2)

    async def test_stale_download_registration_leaves_no_file_row(self):
        await self.change(1, 'begin')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await OutputArchiveService.register_download(
                    db,
                    self.identity,
                    revision=1,
                    worker='archiver',
                    facts=dict(
                        storage_key='media/' + 'e' * 32,
                        sha256='f' * 64,
                        byte_size=72,
                        mime_type='image/png',
                        width=16,
                        height=8,
                    ),
                )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)

    async def test_binding_replay_preserves_job_and_file_identity(self):
        await self.change(1, 'begin')
        renewed = await self.change(2, 'renew')
        self.assertEqual(renewed['revision'], '2')
        result = await self.change(2, 'complete', file_id=self.file_id)
        self.assertEqual(result['archiveState'], 'archived')
        replay = await self.change(2, 'complete', file_id=self.file_id)
        self.assertEqual(replay, result)
        with self.assertRaises(ServiceWarning):
            await self.change(3, 'complete', file_id=self.file_id + 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 2)
            self.assertEqual(
                (
                    await db.execute(
                        text('SELECT orchestration_state,upstream_state,billing_state FROM hf_creation_job')
                    )
                ).one(),
                ('5', '3', '0'),
            )

    async def test_expired_stage_reclaimed_and_old_writer_rejected(self):
        await self.change(1, 'begin')
        with self.assertRaises(ServiceWarning):
            await self.change(2, 'begin')
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_generated_output SET next_retry_time=clock_timestamp()-interval '1 second'")
            )
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.change(2, 'complete', file_id=self.file_id)
        with self.assertRaises(ServiceWarning):
            await self.change(2, 'renew')
        await self.change(2, 'begin')
        with self.assertRaises(ServiceWarning):
            await self.change(2, 'complete', file_id=self.file_id)
        await self.change(3, 'complete', file_id=self.file_id)

    async def test_unready_file_and_event_failure_cannot_mark_archived(self):
        await self.change(1, 'begin')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_stored_file SET state='2'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.change(2, 'complete', file_id=self.file_id)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_stored_file SET state='1'"))
            await db.commit()
        original = JobEventDao.output

        async def fail(*args):
            await original(*args)
            raise RuntimeError('模拟事件写入后故障')

        with patch.object(JobEventDao, 'output', side_effect=fail), self.assertRaises(RuntimeError):
            await self.change(2, 'complete', file_id=self.file_id)
        async with self.sessions() as db:
            self.assertEqual(
                (await db.execute(text('SELECT archive_state,file_id,revision FROM hf_generated_output'))).one(),
                ('1', None, 2),
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 1)

    async def test_source_expiry_and_retry_delay(self):
        await self.change(1, 'begin')
        await self.change(2, 'fail')
        with self.assertRaises(ServiceWarning):
            await self.change(3, 'begin')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_generated_output SET source_expires_time=clock_timestamp()-interval '1 second',next_retry_time=clock_timestamp()-interval '1 second'"
                )
            )
            await db.commit()
        result = await self.change(3, 'begin')
        self.assertEqual(result['archiveState'], 'source_expired')

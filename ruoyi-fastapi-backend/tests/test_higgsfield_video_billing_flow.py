"""同一引用视频任务的上传、提交、查询和结算，使用回环HTTP与隔离数据库。"""
import importlib.util
import asyncio
import hashlib
import os
import shutil
import subprocess
import unittest
from unittest.mock import patch
import httpx
from decimal import Decimal
from pathlib import Path
from sqlalchemy import text
from module_higgsfield.service.billing_worker_service import BillingWorker
from module_higgsfield.service.videoplus_poll_handler import VideoPlusPollHandler
from module_higgsfield.service.output_archive_worker import OutputArchiveWorker
from module_higgsfield.service.output_download_service import OutputDownloadService, OutputDownloadPolicy
from tests import test_higgsfield_videoplus_media_resolver as media
from tests.test_higgsfield_output_discovery import crypto
from tests.test_higgsfield_archive_https import certificates


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class VideoBillingFlowTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = media.MediaResolverTests.cleanup_schema
    migrate = media.MediaResolverTests.migrate
    job = media.MediaResolverTests.job
    write_source = media.MediaResolverTests.write_source
    close_server = media.MediaResolverTests.close_server
    respond = media.MediaResolverTests.respond

    async def asyncSetUp(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('实际视频归档测试需要ffmpeg和ffprobe')
        await media.MediaResolverTests.asyncSetUp(self)
        for filename in ('20261027_33_generated_outputs.py', '20261027_38_usage_records.py', '20261027_39_billing_facts.py'):
            spec = importlib.util.spec_from_file_location('video_flow',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.worker.handlers['poll'] = VideoPlusPollHandler(credential_crypto=self.crypto, output_crypto=crypto())
        root = Path(self.temporary.name)
        video_path = root / 'source.mp4'
        await asyncio.to_thread(subprocess.run, ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
            '-i', 'color=c=blue:s=32x16:r=1', '-t', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            str(video_path)], check=True, capture_output=True, timeout=30)
        self.video_bytes = video_path.read_bytes()
        server_context, self.client_context = await asyncio.to_thread(certificates, root)
        self.downloads = []
        self.download_failed = True
        self.media_server = await asyncio.start_server(self.respond_video, '127.0.0.1', 0, ssl=server_context)
        self.addAsyncCleanup(self.close_media_server)
        port = self.media_server.sockets[0].getsockname()[1]
        self.output_url = f'https://localhost:{port}/result.mp4?signature=test-only'
        downloader = OutputDownloadService(self.storage, OutputDownloadPolicy(
            ('localhost',), 100000, allowed_ports=(port,), local_test=True))
        self.archiver = OutputArchiveWorker(self.sessions, 'video-flow-archive', downloader, crypto())

    async def close_media_server(self):
        self.media_server.close()
        await self.media_server.wait_closed()

    async def respond_video(self, reader, writer):
        try:
            self.downloads.append(await reader.readuntil(b'\r\n\r\n'))
            body = b'unavailable' if self.download_failed else self.video_bytes
            status = '503 Service Unavailable' if self.download_failed else '200 OK'
            writer.write(f'HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\nContent-Type: video/mp4\r\nConnection: close\r\n\r\n'.encode() + body)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_reference_upload_submission_poll_and_billing_share_one_task(self):
        identity = self.lease.job_id
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT upstream_task_id FROM hf_creation_job')), 'task')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), Decimal('6'))
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual([row[0].split(' ')[1] for row in self.requests],
            ['/v1/assets/upload', '/v1/chat/completions', '/v1/video/tasks/task'])
        billing = BillingWorker(self.sessions, 'video-flow-billing')
        self.assertEqual((await billing.process(identity))['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '5')
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_billing_subject WHERE subject_kind='generation'")), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
            # 查询成功只发现输出，不能冒充视频已下载并归档。
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '0')
            rows = (await db.execute(text('SELECT purpose,currency,amount FROM hf_billing_event ORDER BY purpose'))).all()
            self.assertEqual([tuple(row) for row in rows], [
                ('platform', 'CNY', Decimal('0.000246')), ('procurement', 'USD', Decimal('0.000246'))])
            self.assertEqual((await db.execute(text('SELECT reserved_amount,consumed_amount FROM hf_budget_period'))).one(),
                (Decimal('0'), Decimal('0.000246')))
            before = (await db.execute(text('SELECT to_jsonb(e) FROM hf_budget_ledger_entry e ORDER BY entry_id'))).all()
        self.assertEqual(await self.worker.run_once(), [])
        self.assertEqual((await billing.process(identity))['status'], 'skipped')
        self.assertEqual(len(self.requests), 3)
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT to_jsonb(e) FROM hf_budget_ledger_entry e ORDER BY entry_id'))).all(), before)
        transport = httpx.AsyncHTTPTransport
        with patch('httpx.AsyncHTTPTransport', side_effect=lambda **kwargs: transport(verify=self.client_context, **kwargs)):
            self.assertEqual((await self.archiver.run_once())[0]['status'], 'failed')
            async with self.sessions() as db:
                self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
                await db.execute(text("UPDATE hf_generated_output SET next_retry_time=clock_timestamp()-interval '1 second'"))
                await db.commit()
            self.download_failed = False
            self.assertEqual((await self.archiver.run_once())[0]['status'], 'archived')
            self.assertEqual(await self.archiver.run_once(), [])
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT f.storage_key,f.sha256,f.width,f.height,f.seconds,f.mime_type '
                'FROM hf_generated_output o JOIN hf_stored_file f ON f.file_id=o.file_id'))).one()
            self.assertEqual((row.width, row.height, row.seconds, row.mime_type), (32, 16, Decimal('1'), 'video/mp4'))
            self.assertEqual(row.sha256, hashlib.sha256(self.video_bytes).hexdigest())
            self.assertEqual((Path(self.temporary.name) / row.storage_key).read_bytes(), self.video_bytes)
            self.assertEqual((await db.execute(text('SELECT to_jsonb(e) FROM hf_budget_ledger_entry e ORDER BY entry_id'))).all(), before)
        self.assertEqual(len(self.downloads), 2)
        self.assertTrue(all(b'Authorization:' not in request for request in self.downloads))
        self.assertEqual(len(self.requests), 3)
        self.assertEqual((await billing.process(identity))['status'], 'skipped')

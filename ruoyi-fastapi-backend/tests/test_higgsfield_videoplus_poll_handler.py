"""工作器、真实HTTP和隔离数据库贯通验证，不访问供应商。"""

import asyncio
import json
import os
import unittest

from sqlalchemy import text

from module_higgsfield.service.generation_worker_service import GenerationWorkerService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.videoplus_poll_handler import VideoPlusPollHandler
from tests import test_higgsfield_provider_poll as polling
from tests.test_higgsfield_output_discovery import crypto


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class VideoPlusPollHandlerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = polling.ProviderPollTests.cleanup_schema
    migrate = polling.ProviderPollTests.migrate
    job = polling.ProviderPollTests.job
    claim = polling.ProviderPollTests.claim

    async def asyncSetUp(self) -> None:
        await polling.ProviderPollTests.asyncSetUp(self)
        self.requests = []
        self.errors = []
        self.mode = 'success'
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0)
        self.addAsyncCleanup(self.close_server)
        port = self.server.sockets[0].getsockname()[1]
        config = {
            'allowedHosts': ['127.0.0.1'],
            'connectTimeoutSeconds': 1,
            'readTimeoutSeconds': 2,
            'operationTimeoutSeconds': 3,
            'taskTimeoutSeconds': 60,
        }
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_provider_connection_version SET base_url=:url, adapter_version='videoplus-v1', "
                    'config=CAST(:config AS jsonb)'
                ),
                {'url': f'http://127.0.0.1:{port}/', 'config': json.dumps(config)},
            )
            await db.commit()
            await JobLeaseService.release(db, self.lease, retry_after_seconds=0)
        self.worker = GenerationWorkerService(
            self.sessions,
            'http-poll-worker',
            {
                'poll': VideoPlusPollHandler(credential_crypto=self.crypto, output_crypto=crypto()),
            },
        )

    async def close_server(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await reader.readuntil(b'\r\n\r\n')
            self.requests.append(request.split(b'\r\n')[0])
            # 独立连接立即拿到任务锁，并读到已提交的调用意图，证明网络阶段没有占用该事务。
            async with self.sessions() as db:
                await db.execute(text('SELECT job_id FROM hf_creation_job FOR UPDATE NOWAIT'))
                count = await db.scalar(
                    text("SELECT count(*) FROM hf_provider_call WHERE operation='video_poll' AND state='1'")
                )
                if count != 1:
                    self.errors.append('查询意图未在网络调用前提交')
            body = {
                'id': 'video-task',
                'status': 'succeeded',
                'content': {'video_url': 'https://example.com/video?signature=secret'},
                'usage': {'completion_tokens': 123},
            }
            status = '200 OK'
            if self.mode == 'failure':
                status, body = '500 Internal Server Error', {'error': '模拟供应商故障'}
            data = json.dumps(body).encode()
            writer.write(
                f'HTTP/1.1 {status}\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode() + data
            )
            await writer.drain()
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_worker_http_completion_has_committed_intent_and_no_open_job_lock(self) -> None:
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual(self.requests, [b'GET /v1/video/tasks/video-task HTTP/1.1'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '5')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            metadata = await db.scalar(
                text("SELECT response_metadata FROM hf_provider_call WHERE operation='video_poll'")
            )
            self.assertEqual(metadata['usage']['completionTokens'], '123')
            self.assertNotIn('signature', str(metadata))

    async def test_query_error_does_not_create_a_new_generation(self) -> None:
        self.mode = 'failure'
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            row = (
                await db.execute(text('SELECT orchestration_state,upstream_state,lease_owner FROM hf_creation_job'))
            ).one()
            self.assertEqual(tuple(row), ('4', '6', None))
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_provider_call WHERE operation='video_submit'")), 1
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 0)

"""真实文件、上传HTTP与引用生成提交链路，使用隔离数据库及回环服务。"""

import asyncio
import hashlib
import json
import os
import tempfile
import unittest

from sqlalchemy import text

from module_higgsfield.entity.vo.provider_media_policy_vo import ProviderMediaPolicies
from module_higgsfield.service.generation_worker_service import GenerationWorkerService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from module_higgsfield.service.videoplus_media_resolver import VideoPlusMediaResolver
from module_higgsfield.service.videoplus_submit_handler import VideoPlusSubmitHandler
from tests import test_higgsfield_provider_upload_service as uploads


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class MediaResolverTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = uploads.ProviderUploadServiceTests.cleanup_schema
    migrate = uploads.ProviderUploadServiceTests.migrate
    job = uploads.ProviderUploadServiceTests.job

    async def asyncSetUp(self) -> None:
        await uploads.ProviderUploadServiceTests.asyncSetUp(self)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.storage = StorageService(StoragePolicy(self.temporary.name, 'local-test', '', 100000, 100000))
        self.data = b'test-image-bytes'
        self.key = 'media/' + 'a' * 32
        await asyncio.to_thread(self.write_source)
        self.requests, self.errors = [], []
        self.mode = 'success'
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0)
        self.addAsyncCleanup(self.close_server)
        port = self.server.sockets[0].getsockname()[1]
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET kind='video'"))
            await db.execute(text("UPDATE hf_model_profile SET kind='video'"))
            await db.execute(
                text(
                    "UPDATE hf_model_profile_version SET capabilities=jsonb_set(capabilities,'{referenceRules}',CAST(:rules AS jsonb))"
                ),
                {
                    'rules': json.dumps(
                        {
                            'maxTotal': 1,
                            'roles': {'first_frame': {'mediaTypes': ['image'], 'minCount': 1, 'maxCount': 1}},
                        }
                    )
                },
            )
            await db.execute(
                text('UPDATE hf_stored_file SET storage_key=:key,sha256=:sha,byte_size=:size'),
                {'key': self.key, 'sha': hashlib.sha256(self.data).hexdigest(), 'size': len(self.data)},
            )
            snapshot = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job'))
            item = snapshot['compiled']['media'][0]
            item.update(
                ordinal=0,
                mediaRole='first_frame',
                sha256=hashlib.sha256(self.data).hexdigest(),
                byteSize=str(len(self.data)),
            )
            snapshot['compiled']['promptParagraphs'] = [
                [{'type': 'text', 'text': '参考'}, {'type': 'reference', 'ordinals': [0]}]
            ]
            await db.execute(
                text('UPDATE hf_creation_job SET input_snapshot=CAST(:snapshot AS jsonb)'),
                {'snapshot': json.dumps(snapshot)},
            )
            await db.execute(
                text(
                    "UPDATE hf_provider_connection_version SET base_url=:url,adapter_version='videoplus-v1',config=CAST(:config AS jsonb)"
                ),
                {
                    'url': f'http://127.0.0.1:{port}/',
                    'config': json.dumps(
                        {
                            'allowedHosts': ['127.0.0.1'],
                            'connectTimeoutSeconds': 1,
                            'readTimeoutSeconds': 2,
                            'operationTimeoutSeconds': 3,
                            'taskTimeoutSeconds': 60,
                        }
                    ),
                },
            )
            await db.commit()
            await JobLeaseService.release(db, self.lease, retry_after_seconds=0)
        policies = ProviderMediaPolicies(
            modelVersions={
                str(self.model_version_id): {
                    'roles': ['first_frame'],
                    'mimeLimits': {'image/png': 100000},
                    'requiredSeconds': 60,
                    'evidenceRef': 'test-only',
                }
            }
        )
        resolver = VideoPlusMediaResolver(credential_crypto=self.crypto, policies=policies, storage=self.storage)
        self.worker = GenerationWorkerService(
            self.sessions,
            'reference-worker',
            {
                'prepare': VideoPlusSubmitHandler(credential_crypto=self.crypto, media_resolver=resolver),
            },
        )

    def write_source(self) -> None:
        with self.storage.open_key(self.key, write=True) as handle:
            handle.write(self.data)

    async def close_server(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            header = await reader.readuntil(b'\r\n\r\n')
            lines = header.decode().split('\r\n')
            headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
            body = await reader.readexactly(int(headers.get('Content-Length', '0')))
            self.requests.append((lines[0], body))
            async with self.sessions() as db:
                await db.execute(text('SELECT job_id FROM hf_creation_job FOR UPDATE NOWAIT'))
            if lines[0] == 'GET /v1/video/tasks/task HTTP/1.1':
                response = {'id': 'task', 'status': 'succeeded',
                    'content': {'video_url': getattr(self, 'output_url', 'https://example.com/video?signature=secret')},
                    'usage': {'completion_tokens': 123}}
            elif '/assets/upload ' in lines[0]:
                self.assertIn(self.data, body)
                response = {
                    'success': True,
                    'file_name': 'reference',
                    'asset_type': 'image',
                    'content_type': 'image/png',
                    'size': len(self.data),
                    'url': 'https://example.com/reference?signature=secret',
                    'expires_in': 3600,
                }
                if self.mode == 'unknown':
                    response.pop('expires_in')
                if self.mode == 'revoke_after_upload':
                    async with self.sessions() as db:
                        await db.execute(text("UPDATE sys_role SET status='1'"))
                        await db.commit()
            else:
                payload = json.loads(body)
                content = payload['messages'][0]['content']
                self.assertEqual(content[0]['text'], '参考图片 1')
                self.assertEqual(content[1]['image_url']['url'], 'https://example.com/reference?signature=secret')
                response = {'id': 'outer', 'choices': [{'message': {'content': '{"id":"task"}'}}]}
            encoded = json.dumps(response).encode()
            writer.write(
                f'HTTP/1.1 200 OK\r\nContent-Length: {len(encoded)}\r\nConnection: close\r\n\r\n'.encode() + encoded
            )
            await writer.drain()
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_access_revoked_before_upload_sends_no_media(self):
        changes = (
            ("UPDATE hf_project SET status='1'", "UPDATE hf_project SET status='0'"),
            ("UPDATE sys_user SET status='1'", "UPDATE sys_user SET status='0'"),
            ("UPDATE sys_role SET status='1'", "UPDATE sys_role SET status='0'"),
        )
        for revoke, restore in changes:
            with self.subTest(revoke=revoke):
                async with self.sessions() as db:
                    await db.execute(text(revoke))
                    await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
                    await db.commit()
                self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
                self.assertEqual(self.requests, [])
                async with self.sessions() as db:
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_upload')), 0)
                    self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '1')
                    await db.execute(text(restore))
                    await db.commit()

    async def test_revocation_during_upload_blocks_generation_and_reuses_saved_upload(self):
        self.mode = 'revoke_after_upload'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertEqual([item[0].split(' ')[1] for item in self.requests], ['/v1/assets/upload'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_upload')), '1')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '1')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            await db.execute(text("UPDATE sys_role SET status='0'"))
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.mode = 'success'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual([item[0].split(' ')[1] for item in self.requests],
                         ['/v1/assets/upload', '/v1/chat/completions'])
        self.assertEqual(self.errors, [])

    async def test_upload_then_submit_reference_without_nas_path(self) -> None:
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual(
            [item[0].split(' ')[1] for item in self.requests], ['/v1/assets/upload', '/v1/chat/completions']
        )
        self.assertNotIn(self.temporary.name.encode(), self.requests[1][1])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '4')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)

    async def test_unconfirmed_upload_never_submits_generation(self) -> None:
        self.mode = 'unknown'
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handler_failed')
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_upload')), '3')
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '1')

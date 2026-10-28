"""真实HTTP图片生成响应→真实图片落盘→隔离数据库完成登记。"""

import asyncio
import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from PIL import Image
from sqlalchemy import text

from module_higgsfield.service.image_worker_runtime import create_image_worker, create_image_recovery_worker
from module_higgsfield.service.image_result_service import ImageResultService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from tests import test_higgsfield_videoplus_submit_handler as video
from tests.test_higgsfield_image_request import capability, snapshot


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ImageSubmitHandlerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = video.VideoPlusSubmitHandlerTests.cleanup_schema
    migrate = video.VideoPlusSubmitHandlerTests.migrate
    job = video.VideoPlusSubmitHandlerTests.job
    close_server = video.VideoPlusSubmitHandlerTests.close_server
    test_revoked_access_never_reaches_http_and_restored_access_submits_once = (
        video.VideoPlusSubmitHandlerTests.test_revoked_access_never_reaches_http_and_restored_access_submits_once
    )

    async def asyncSetUp(self):
        await video.VideoPlusSubmitHandlerTests.asyncSetUp(self)
        for name in (
            '20261027_06_assets.py',
            '20261027_33_generated_outputs.py',
            '20261027_38_usage_records.py',
        ):
            spec = importlib.util.spec_from_file_location(
                'image_handler_tables', video.intent.pipeline.MIGRATIONS / name
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET kind='image', input_snapshot=input_snapshot || CAST(:snapshot AS jsonb)"
                ),
                {'snapshot': json.dumps(snapshot())},
            )
            await db.execute(text("UPDATE hf_model_profile SET kind='image'"))
            await db.execute(
                text(
                    "UPDATE hf_model_profile_version SET gateway_alias='mm-imagen2', capabilities=CAST(:cap AS jsonb)"
                ),
                {'cap': capability().model_dump_json(by_alias=True)},
            )
            await db.commit()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        buffer = io.BytesIO()
        Image.new('RGB', (16, 16), 'blue').save(buffer, format='PNG')
        self.data = buffer.getvalue()
        storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 100000, 10000))
        self.worker = create_image_worker(
            self.sessions, 'image-http', storage=storage, credential_crypto=self.crypto, max_decoded_bytes=100000
        )
        self.image_storage = self.worker.handlers['prepare'].storage
        self.evidence_storage = self.worker.handlers['prepare'].evidence_storage

    async def respond(self, reader, writer):
        try:
            header = await reader.readuntil(b'\r\n\r\n')
            headers = dict(line.split(': ', 1) for line in header.decode().split('\r\n')[1:] if ': ' in line)
            self.requests.append(json.loads(await reader.readexactly(int(headers['Content-Length']))))
            async with self.sessions() as db:
                state = await db.scalar(text('SELECT orchestration_state FROM hf_creation_job FOR UPDATE NOWAIT'))
                self.assertEqual(state, '2')
                self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            inner = json.dumps(
                {
                    'images': [{'b64_json': base64.b64encode(self.data).decode()}],
                    'usage': {'input_tokens': 12, 'output_tokens': 34},
                    'output_format': 'png',
                }
            )
            if self.mode == 'unknown':
                inner = 'invalid-json'
            body = json.dumps({'id': 'image-http-result', 'choices': [{'message': {'content': inner}}]}).encode()
            writer.write(f'HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode() + body)
            await writer.drain()
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_complete_image_is_stored_and_usage_is_preserved(self):
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual(self.requests[0]['model'], 'mm-imagen2')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '5')
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '2')
            key = await db.scalar(text('SELECT storage_key FROM hf_stored_file'))
            usage = await db.scalar(text("SELECT response_metadata->'usage' FROM hf_provider_call"))
            self.assertEqual(usage, {'input_tokens': '12', 'output_tokens': '34'})
            self.assertEqual(
                (await db.execute(text('SELECT input_tokens,output_tokens,completeness FROM hf_usage_record'))).one(),
                (12, 34, 'available'),
            )
        self.assertEqual(await asyncio.to_thread((Path(self.temp.name) / key).read_bytes), self.data)
        self.assertEqual(await self.worker.run_once(), [])

    async def test_failed_image_keeps_decryptable_response_evidence(self):
        with patch.object(self.image_storage, 'persist', AsyncMock(side_effect=ValueError('模拟归档失败'))):
            self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
            row = (
                (
                    await db.execute(
                        text('SELECT provider_call_id,job_id,storage_key,sha256,byte_size FROM hf_provider_response')
                    )
                )
                .mappings()
                .one()
            )
            facts = {key: row[key] for key in ('storage_key', 'sha256', 'byte_size')}
            call_id, job_id = row['provider_call_id'], row['job_id']
        body = await self.evidence_storage.load(facts, call_id, job_id)
        inner = json.loads(body['choices'][0]['message']['content'])
        self.assertEqual(base64.b64decode(inner['images'][0]['b64_json']), self.data)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(await self.worker.run_once(), [])
        recovery = create_image_recovery_worker(
            self.sessions,
            'image-recovery',
            storage=self.image_storage.storage,
            credential_crypto=self.crypto,
            max_decoded_bytes=100000,
        )
        batches = await asyncio.gather(recovery.run_once(), recovery.run_once())
        statuses = [row['status'] for batch in batches for row in batch]
        self.assertEqual(statuses.count('archived'), 1)
        self.assertTrue(all(status in {'archived', 'skipped'} for status in statuses))
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(await recovery.run_once(), [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_response')), 1)
            metadata = await db.scalar(text('SELECT actual_metadata FROM hf_generated_output'))
            self.assertEqual((metadata['width'], metadata['height'], metadata['format']), (16, 16, 'png'))
            usage = await db.scalar(text("SELECT response_metadata->'usage' FROM hf_provider_call"))
            self.assertEqual(usage, {'input_tokens': '12', 'output_tokens': '34'})

    async def test_unknown_response_is_not_resubmitted(self):
        self.mode = 'unknown'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')

    async def test_interrupted_completion_recovers_from_evidence_without_resubmit(self):
        with patch.object(ImageResultService, 'record', AsyncMock(side_effect=RuntimeError('模拟完成前中断'))):
            self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_response')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 0)
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '5')
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            metadata = await db.scalar(text('SELECT response_metadata FROM hf_provider_call'))
            evidence_id = await db.scalar(text('SELECT response_evidence_id FROM hf_provider_response'))
            self.assertEqual(metadata['recoveredEvidenceId'], str(evidence_id))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_usage_record')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 1)
            self.assertEqual(metadata['usage'], {'input_tokens': '12', 'output_tokens': '34'})
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')

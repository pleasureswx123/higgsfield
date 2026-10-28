"""提交工作器经真实回环HTTP受理，未知结果不能重复生成。"""

import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult

from module_higgsfield.service.generation_worker_service import GenerationWorkerService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.video_worker_runtime import create_video_worker
from module_higgsfield.service.videoplus_submit_handler import VideoPlusSubmitHandler
from module_higgsfield.service.provider_submission_result_service import ProviderSubmissionResultService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from tests import test_higgsfield_provider_submit_intent as intent
from tests.test_higgsfield_output_discovery import crypto


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class VideoPlusSubmitHandlerTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = intent.SubmitIntentTests.cleanup_schema
    migrate = intent.SubmitIntentTests.migrate
    job = intent.SubmitIntentTests.job

    async def asyncSetUp(self) -> None:
        await intent.SubmitIntentTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'video_responses', intent.pipeline.MIGRATIONS / '20261027_37_provider_responses.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.storage = StorageService(StoragePolicy(self.temporary.name, 'local-test', '', 100000, 100000))
        self.requests, self.errors = [], []
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
            await db.execute(text("UPDATE hf_creation_job SET kind='video'"))
            await db.execute(text("UPDATE hf_model_profile SET kind='video'"))
            await db.execute(text("UPDATE hf_model_profile_version SET gateway_alias='mm-eva-sd-2.5'"))
            await db.execute(
                text(
                    "UPDATE hf_provider_connection_version SET base_url=:url, adapter_version='videoplus-v1', config=CAST(:config AS jsonb)"
                ),
                {'url': f'http://127.0.0.1:{port}/', 'config': json.dumps(config)},
            )
            await db.commit()
            await JobLeaseService.release(db, self.lease, retry_after_seconds=0)
        self.worker = GenerationWorkerService(
            self.sessions,
            'submit-http',
            {
                'prepare': VideoPlusSubmitHandler(credential_crypto=self.crypto),
            },
        )

    async def close_server(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def test_revoked_access_never_reaches_http_and_restored_access_submits_once(self):
        """实际工作器经过三道门槛；拒绝时不能把任务误记为提交未知。"""
        async with self.sessions() as db:
            original = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job'))
            ledger = list(await db.scalars(text('SELECT to_jsonb(l) FROM hf_budget_ledger_entry l ORDER BY entry_id')))
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
                self.assertEqual(self.errors, [])
                async with self.sessions() as db:
                    row = (await db.execute(text(
                        'SELECT orchestration_state,lease_owner,upstream_task_id,input_snapshot FROM hf_creation_job'
                    ))).one()
                    self.assertEqual(tuple(row), ('1', None, None, original))
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                    self.assertEqual(list(await db.scalars(text(
                        'SELECT to_jsonb(l) FROM hf_budget_ledger_entry l ORDER BY entry_id'
                    ))), ledger)
                    await db.execute(text(restore))
                    await db.commit()
                # 释放租约后仍遵守重试延迟，不能立刻循环占用任务。
                self.assertEqual(await self.worker.run_once(), [])
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.errors, [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            header = await reader.readuntil(b'\r\n\r\n')
            lines = header.decode().split('\r\n')
            headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
            is_poll = lines[0].startswith('GET ')
            payload = None if is_poll else json.loads(await reader.readexactly(int(headers['Content-Length'])))
            self.requests.append((lines[0], payload))
            async with self.sessions() as db:
                row = (
                    await db.execute(
                        text("SELECT orchestration_state FROM hf_creation_job WHERE kind='video' FOR UPDATE NOWAIT")
                    )
                ).scalar_one()
                count = await db.scalar(
                    text("SELECT count(*) FROM hf_provider_call WHERE operation=:operation AND state='1'"),
                    {'operation': 'video_poll' if is_poll else 'video_submit'},
                )
                if row != ('4' if is_poll else '2') or count != 1:
                    self.errors.append('发送意图未提交')
            inner = json.dumps({'id': 'accepted-task', 'status': 'queued'}) if self.mode == 'success' else 'broken json'
            body = json.dumps({'id': 'outer-response', 'choices': [{'message': {'content': inner}}]}).encode()
            if is_poll:
                body = json.dumps(
                    {
                        'id': 'accepted-task',
                        'status': 'succeeded',
                        'content': {'video_url': 'https://example.com/result'},
                        'usage': {'completion_tokens': 123},
                    }
                ).encode()
            writer.write(f'HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode() + body)
            await writer.drain()
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_submit_fixed_payload_and_record_acceptance(self) -> None:
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual(len(self.requests), 1)
        request, payload = self.requests[0]
        self.assertEqual(request, 'POST /v1/chat/completions HTTP/1.1')
        self.assertEqual(
            payload,
            {
                'model': 'mm-eva-sd-2.5',
                'messages': [{'role': 'user', 'content': ''}],
                'duration': 6,
                'resolution': '720p',
                'generate_audio': False,
            },
        )
        async with self.sessions() as db:
            row = (
                await db.execute(
                    text('SELECT orchestration_state,upstream_task_id,upstream_response_id FROM hf_creation_job')
                )
            ).one()
            self.assertEqual(tuple(row), ('4', 'accepted-task', 'outer-response'))
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_unclear_acceptance_never_resubmits(self) -> None:
        self.mode = 'unknown'
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'handler_unavailable')
        self.assertEqual(len(self.requests), 1)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)

    async def test_runtime_submit_then_poll_and_skip_image_jobs(self) -> None:
        spec = importlib.util.spec_from_file_location(
            'runtime_usage', intent.pipeline.MIGRATIONS / '20261027_38_usage_records.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location(
            'runtime_outputs', intent.pipeline.MIGRATIONS / '20261027_33_generated_outputs.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            db.add(self.job(kind='image', idempotency_key='other-image'))
            await db.flush()
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second' WHERE kind='image'"
                )
            )
            await db.commit()
        worker = create_video_worker(
            self.sessions, 'runtime-video', credential_crypto=self.crypto, output_crypto=crypto(), storage=self.storage
        )
        first = await worker.run_once()
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]['status'], 'handled')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second' WHERE kind='video'"
                )
            )
            await db.commit()
        second = await worker.run_once()
        self.assertEqual(second[0]['status'], 'handled')
        self.assertEqual(self.errors, [])
        self.assertEqual([item[0].split(' ')[0] for item in self.requests], ['POST', 'GET'])
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(text("SELECT orchestration_state FROM hf_creation_job WHERE kind='video'")), '5'
            )
            self.assertEqual(await db.scalar(text("SELECT fencing_token FROM hf_creation_job WHERE kind='image'")), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)

    async def test_saved_acceptance_recovers_after_database_failure_without_resubmission(self):
        worker = create_video_worker(
            self.sessions, 'video-recovery', credential_crypto=self.crypto, output_crypto=crypto(), storage=self.storage
        )
        with patch.object(ProviderSubmissionResultService, 'record', AsyncMock(side_effect=RuntimeError('状态写入故障'))):
            self.assertEqual((await worker.run_once())[0]['status'], 'handler_failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_response')), 1)
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            row = (await db.execute(text(
                'SELECT orchestration_state,upstream_task_id,upstream_response_id FROM hf_creation_job'
            ))).one()
            self.assertEqual(tuple(row), ('4', 'accepted-task', 'outer-response'))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            metadata = await db.scalar(text('SELECT response_metadata FROM hf_provider_call'))
            self.assertTrue(metadata['recoveryEvidenceId'].isdigit())
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.errors, [])

    async def test_ambiguous_saved_response_stays_unknown_without_resubmission(self):
        self.mode = 'unknown'
        worker = create_video_worker(
            self.sessions, 'video-unknown', credential_crypto=self.crypto, output_crypto=crypto(), storage=self.storage
        )
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_response')), 1)
        self.assertEqual(len(self.requests), 1)

    async def test_corrupt_evidence_cannot_restore_acceptance(self):
        worker = create_video_worker(
            self.sessions, 'video-corrupt', credential_crypto=self.crypto, output_crypto=crypto(), storage=self.storage
        )
        with patch.object(ProviderSubmissionResultService, 'record', AsyncMock(side_effect=RuntimeError('状态写入故障'))):
            await worker.run_once()
        async with self.sessions() as db:
            key = await db.scalar(text('SELECT storage_key FROM hf_provider_response'))
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        (Path(self.temporary.name) / key).write_bytes(b'corrupt')
        self.assertEqual((await worker.run_once())[0]['status'], 'handler_failed')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            self.assertIsNone(await db.scalar(text('SELECT upstream_task_id FROM hf_creation_job')))
        self.assertEqual(len(self.requests), 1)

    async def test_recovery_checks_evidence_identity_and_rolls_back_event_failure(self):
        worker = create_video_worker(
            self.sessions, 'video-identity', credential_crypto=self.crypto, output_crypto=crypto(), storage=self.storage
        )
        with patch.object(ProviderSubmissionResultService, 'record', AsyncMock(side_effect=RuntimeError('状态写入故障'))):
            await worker.run_once()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
            lease = (await JobLeaseService.claim(db, 'identity-check', limit=1))[0]
            call_id = await db.scalar(text('SELECT call_id FROM hf_provider_call'))
            evidence_id = await db.scalar(text('SELECT response_evidence_id FROM hf_provider_response'))
            await db.rollback()
        fact = ProviderSubmissionResult(
            acceptance='accepted', transport='response', httpStatus=200,
            upstreamTaskId='accepted-task', responseId='outer-response',
        )
        for identity, result in ((evidence_id + 1, fact), (True, fact),
                                 (evidence_id, fact.model_copy(update={'http_status': 201}))):
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning):
                    await ProviderSubmissionResultService.record(
                        db, lease, call_id, result, recovery_evidence_id=identity
                    )
        async with self.sessions() as db:
            with patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))):
                with self.assertRaises(RuntimeError):
                    await ProviderSubmissionResultService.record(
                        db, lease, call_id, fact, recovery_evidence_id=evidence_id
                    )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '3')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '3')
            await db.rollback()
            await JobLeaseService.release(db, lease, retry_after_seconds=0)
        self.assertEqual((await worker.run_once())[0]['status'], 'handled')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ProviderSubmissionResultService.record(
                    db, lease, call_id, fact, recovery_evidence_id=evidence_id
                )
        self.assertEqual(len(self.requests), 1)

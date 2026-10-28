"""输出加密、发现去重与原子性测试。"""

import os
import unittest
from unittest.mock import patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.output_discovery_service import OutputDiscoveryService
from module_higgsfield.dao.job_event_dao import JobEventDao
from tests import test_higgsfield_generated_outputs as outputs
from tests import test_higgsfield_job_leases as leases


def crypto():
    return OutputSourceCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32))


class OutputCryptoTests(unittest.TestCase):
    def test_context_tamper_and_random_nonce(self):
        service = crypto()
        url = 'https://example.com/file?signature=secret-value'
        encrypted = service.encrypt(url, 1, 0)
        self.assertNotIn(b'secret-value', encrypted)
        self.assertEqual(service.decrypt(encrypted, 1, 0), url)
        self.assertNotEqual(encrypted, service.encrypt(url, 1, 0))
        for identity, ordinal in ((2, 0), (1, 1)):
            with self.assertRaises(ServiceWarning):
                service.decrypt(encrypted, identity, ordinal)
        with self.assertRaises(ServiceWarning):
            service.decrypt(b'bad-envelope', 1, 0)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class OutputDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = outputs.GeneratedOutputTests.cleanup_schema
    migrate = outputs.GeneratedOutputTests.migrate
    asyncSetUp = outputs.GeneratedOutputTests.asyncSetUp
    job = leases.JobLeaseTests.job
    seed = leases.JobLeaseTests.seed
    claim = leases.JobLeaseTests.claim

    async def record(self, lease, batch, **kwargs):
        async with self.sessions() as db:
            db.autoflush = False
            return await OutputDiscoveryService.record(db, lease, batch, crypto=crypto(), **kwargs)

    async def test_sync_completion_has_outputs_before_success_without_fake_task_id(self):
        from module_higgsfield.service.job_transition_service import JobTransitionService

        await self.seed()
        lease = (await self.claim('sync-worker'))[0]
        async with self.sessions() as db:
            lease = await JobTransitionService.apply(db, lease, action='prepare')
            lease = await JobTransitionService.apply(db, lease, action='submit')
        completed = await self.record(
            lease,
            [
                DiscoveredOutput(ordinal=0, kind='image', sourceUrl='https://example.com/0'),
                DiscoveredOutput(ordinal=1, kind='image', sourceUrl='https://example.com/1'),
            ],
            complete=True,
        )
        self.assertEqual(completed.revision, lease.revision + 1)
        async with self.sessions() as db:
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_state,billing_state,upstream_task_id,lease_owner,next_action_time FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(row, ('5', '3', '0', None, None, None))
            self.assertEqual(
                await db.scalar(
                    text("SELECT count(*) FROM hf_generated_output WHERE archive_state='0' AND file_id IS NULL")
                ),
                2,
            )
            events = (await db.execute(text('SELECT event_type,payload FROM hf_task_event ORDER BY sequence'))).all()
            self.assertEqual(
                [event[0] for event in events],
                ['task.state', 'task.state', 'output.state', 'output.state', 'task.state'],
            )
            self.assertEqual(events[-1][1]['upstreamState'], 'succeeded')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 5)
        self.assertEqual(await self.claim('next-worker'), [])

    async def test_final_state_event_failure_rolls_back_outputs_and_success(self):
        await self.seed(orchestration_state='4', upstream_state='2')
        lease = (await self.claim('worker'))[0]
        original = JobEventDao.state

        async def fail(*args):
            await original(*args)
            raise RuntimeError('模拟最终状态提交故障')

        with patch.object(JobEventDao, 'state', side_effect=fail), self.assertRaises(RuntimeError):
            await self.record(lease, [DiscoveredOutput(ordinal=0, kind='text', text='结果')], complete=True)
        async with self.sessions() as db:
            row = (
                await db.execute(
                    text(
                        'SELECT orchestration_state,upstream_state,revision,event_sequence,lease_owner FROM hf_creation_job'
                    )
                )
            ).one()
            self.assertEqual(row, ('4', '2', 1, 0, 'worker'))
            for table in ('hf_generated_output', 'hf_task_event', 'hf_outbox_event'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM ' + table)), 0)

    async def test_discovery_replay_preserves_identity_and_cost(self):
        await self.seed(orchestration_state='4', upstream_state='2', billing_state='3')
        lease = (await self.claim('worker'))[0]
        batch = [DiscoveredOutput(ordinal=0, kind='image', sourceUrl='https://example.com/a?token=private')]
        newer = await self.record(lease, batch)
        replay = await self.record(newer, batch)
        self.assertEqual(newer.revision, replay.revision)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '3')
            payload = await db.scalar(text('SELECT payload FROM hf_task_event'))
            self.assertNotIn('private', str(payload))
            encrypted = await db.scalar(text('SELECT source_url_ciphertext FROM hf_generated_output'))
            self.assertEqual(crypto().decrypt(encrypted, lease.job_id, 0), 'https://example.com/a?token=private')
        with self.assertRaises(ServiceWarning):
            await self.record(lease, batch)

    async def test_conflict_rolls_back_new_rows_in_same_batch(self):
        await self.seed(orchestration_state='4')
        lease = (await self.claim('worker'))[0]
        lease = await self.record(lease, [DiscoveredOutput(ordinal=2, kind='text', text='原结果')])
        with self.assertRaises(ServiceWarning):
            await self.record(
                lease,
                [
                    DiscoveredOutput(ordinal=1, kind='text', text='新增'),
                    DiscoveredOutput(ordinal=2, kind='text', text='冲突'),
                ],
            )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 1)

    async def test_event_failure_rolls_back_all_outputs(self):
        await self.seed(orchestration_state='4')
        lease = (await self.claim('worker'))[0]
        original = JobEventDao.output

        async def fail(*args):
            await original(*args)
            raise RuntimeError('模拟事件提交故障')

        with patch.object(JobEventDao, 'output', side_effect=fail), self.assertRaises(RuntimeError):
            await self.record(lease, [DiscoveredOutput(ordinal=0, kind='text', text='文本')])
        async with self.sessions() as db:
            for table in ('hf_generated_output', 'hf_task_event', 'hf_outbox_event'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM ' + table)), 0)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)

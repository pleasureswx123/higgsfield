"""排空与撤销不丢失原凭据依赖，不推断上游免费。"""

import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from module_higgsfield.entity.vo.credential_vo import CredentialStateAction, CredentialVersionCreate
from module_higgsfield.service.credential_state_service import CredentialStateService
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.service.write_service import WriteService
from exceptions.exception import ServiceWarning, PermissionException
from tests import test_higgsfield_credentials as credentials


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialStateTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = credentials.CredentialTests.cleanup_schema
    payload = credentials.CredentialTests.payload
    save = credentials.CredentialTests.save

    async def asyncSetUp(self):
        await credentials.CredentialTests.asyncSetUp(self)
        self.owner.user.admin = True
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_user ADD COLUMN dept_id bigint'))
        result, _ = await self.save()
        self.identity = int(result['data']['id'])
        self.key_id = int(result['data']['versionsSummary'][0]['id'])
        async with self.sessions() as db:
            # 仅准备已启用状态用于生命周期验证，不冒充真实凭据测试。
            await db.execute(
                text("UPDATE hf_credential_version SET state='1' WHERE credential_version_id=:id"), {'id': self.key_id}
            )
            await db.execute(
                text("UPDATE hf_provider_credential SET status='1' WHERE credential_id=:id"), {'id': self.identity}
            )
            await db.commit()

    async def act(self, action, revision='1', key=None):
        async with self.sessions() as db:
            # 与正式会话一致，关闭自动刷新，确保身份状态由显式刷新后汇总。
            db.autoflush = False
            return await CredentialStateService.mutate(
                db,
                self.owner,
                self.key_id,
                action,
                CredentialStateAction(revision=revision, reason='测试状态治理'),
                key or str(uuid4()),
            )

    async def add_job(self):
        async with self.sessions() as db:
            db.add(
                HfCreationJob(
                    project_id=1,
                    actor_id=1,
                    department_snapshot={},
                    kind='image',
                    idempotency_key='inflight',
                    request_hash='a' * 64,
                    model_version_id=1,
                    model_variant_id=1,
                    credential_version_id=self.key_id,
                    platform_price_version_id=1,
                    input_snapshot={},
                    orchestration_state='4',
                    upstream_state='2',
                    **WriteService.audit(self.owner),
                )
            )
            await db.commit()

    async def test_drain_replay_and_disable_after_jobs_finish(self):
        await self.add_job()
        key = str(uuid4())
        result, _ = await self.act('drain', key=key)
        repeated, replay = await self.act('drain', key=key)
        self.assertTrue(replay)
        self.assertEqual(result, repeated)
        self.assertEqual(result['data']['state'], 'draining')
        with self.assertRaises(ServiceWarning):
            await self.act('disable', revision='2')
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(
                    text('SELECT status FROM hf_provider_credential WHERE credential_id=:id'), {'id': self.identity}
                ),
                '2',
            )
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',upstream_state='3'"))
            await db.commit()
        result, _ = await self.act('disable', revision='2')
        self.assertEqual(result['data']['state'], 'disabled')
        with self.assertRaises(ServiceWarning):
            await self.act('drain', revision='3')

    async def test_revoke_preserves_job_and_ciphertext(self):
        await self.add_job()
        async with self.sessions() as db:
            secret = await db.scalar(
                text('SELECT secret_ciphertext FROM hf_credential_version WHERE credential_version_id=:id'),
                {'id': self.key_id},
            )
        result, _ = await self.act('revoke')
        self.assertEqual(result['data']['inFlightCount'], '1')
        self.assertEqual(result['data']['state'], 'revoked')
        async with self.sessions() as db:
            row = (
                await db.execute(text('SELECT credential_version_id,upstream_state,billing_state FROM hf_creation_job'))
            ).one()
            self.assertEqual(row, (self.key_id, '2', '0'))
            self.assertEqual(
                await db.scalar(
                    text('SELECT secret_ciphertext FROM hf_credential_version WHERE credential_version_id=:id'),
                    {'id': self.key_id},
                ),
                secret,
            )
            self.assertIsNotNone(
                await db.scalar(
                    text('SELECT revoked_time FROM hf_credential_version WHERE credential_version_id=:id'),
                    {'id': self.key_id},
                )
            )

    async def test_active_sibling_is_not_disabled_and_permission_required(self):
        rotated, _ = await self.save(
            CredentialVersionCreate(
                revision='1',
                connectionVersionId=self.version_id,
                apiKey='new-test-key-12345',
                validFrom='2026-01-01T00:00:00Z',
            ),
            credential_id=self.identity,
        )
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_credential_version SET state='1' WHERE credential_version_id=:id"),
                {'id': int(rotated['data']['id'])},
            )
            await db.commit()
        await self.act('drain')
        await self.act('disable', revision='2')
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(
                    text('SELECT status FROM hf_provider_credential WHERE credential_id=:id'), {'id': self.identity}
                ),
                '1',
            )
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.act('revoke', revision='3')

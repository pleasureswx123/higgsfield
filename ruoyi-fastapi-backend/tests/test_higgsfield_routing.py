"""整组路由的实际迁移、并发与跨供应商隔离测试。"""

import asyncio
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.do.model_do import HfModelProfile, HfModelProfileVersion
from module_higgsfield.entity.vo.routing_vo import RoutingUpdate
from module_higgsfield.entity.vo.project_vo import ProjectCreate
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.credential_service import CredentialService
from module_higgsfield.service.routing_service import RoutingService
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_credentials as credentials


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RoutingTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = credentials.CredentialTests.cleanup_schema

    async def asyncSetUp(self):
        await credentials.CredentialTests.asyncSetUp(self)
        self.owner.user.admin = True
        async with self.engine.begin() as conn:
            await conn.execute(text('ALTER TABLE sys_user ADD COLUMN dept_id bigint'))
        async with self.sessions() as db:
            project, _ = await ProjectService.create_project(
                db, self.owner, ProjectCreate(name='路由测试'), str(uuid4())
            )
            self.project_id = int(project['data']['id'])
            credential, _ = await CredentialService.save(
                db, self.owner, credentials.CredentialTests.payload(self), str(uuid4()), crypto=self.crypto
            )
            self.credential_id = credential['data']['id']
            self.connection_id = await db.scalar(
                text('SELECT connection_id FROM hf_provider_account WHERE account_id=:id'), {'id': int(self.account_id)}
            )
            model = await ProviderDao.add(
                db,
                HfModelProfile,
                connection_id=self.connection_id,
                code='route-test',
                display_name='路由测试模型',
                kind='image',
                **WriteService.audit(self.owner),
            )
            self.model_id = str(model.model_id)
            await ProviderDao.add(
                db,
                HfModelProfileVersion,
                model_id=model.model_id,
                version_no=1,
                gateway_alias='test',
                region='eva',
                capabilities={},
                schema_version=1,
                status='0',
                revision=1,
                **WriteService.audit(self.owner),
            )
            await db.commit()

    def payload(self, revision='1', enabled=False, **changes):
        route = dict(
            modelId=self.model_id,
            accountId=self.account_id,
            priority=100,
            enabled=enabled,
            credentials=[dict(credentialId=self.credential_id, priority=100, maxConcurrency=2)],
        )
        route.update(changes)
        return RoutingUpdate(revision=revision, routes=[route])

    async def save(self, payload=None, key=None):
        async with self.sessions() as db:
            return await RoutingService.save(
                db, self.owner, self.project_id, payload or self.payload(), key or str(uuid4())
            )

    async def test_replay_cas_atomic_replace_and_account_scope(self):
        key = str(uuid4())
        first, _ = await self.save(key=key)
        again, replay = await self.save(key=key)
        self.assertTrue(replay)
        self.assertEqual(first, again)
        self.assertEqual(first['data']['revision'], '2')
        with self.assertRaises(ServiceWarning):
            await self.save()
        with self.assertRaises(ServiceWarning):
            await self.save(self.payload(revision='2', accountId='99999'))
        with self.assertRaises(ServiceWarning):
            await self.save(
                self.payload(revision='2', credentials=[dict(credentialId='99999', priority=1, maxConcurrency=1)])
            )
        async with self.sessions() as db:
            current = await RoutingService.get(db, self.owner, self.project_id)
            self.assertEqual(current, first['data'])
        cleared, _ = await self.save(RoutingUpdate(revision='2', routes=[]))
        self.assertEqual(cleared['data']['routes'], [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_routing_policy')), 0)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='project_routing_set'")), 2
            )

    async def test_enabled_requires_current_active_unexpired_dependencies(self):
        with self.assertRaises(ServiceWarning):
            await self.save(self.payload(enabled=True))
        # 模拟已通过独立激活流程的状态，仅用于验证路由准入，不表示真实供应商测试通过。
        async with self.sessions() as db:
            for sql in (
                "UPDATE hf_provider_connection SET status='1'",
                "UPDATE hf_model_profile_version SET status='2'",
                "UPDATE hf_provider_credential SET status='1'",
                "UPDATE hf_credential_version SET state='1'",
            ):
                await db.execute(text(sql))
            await db.commit()
        result, _ = await self.save(self.payload(enabled=True))
        self.assertTrue(result['data']['routes'][0]['enabled'])
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_credential_version SET valid_until='2026-01-02T00:00:00Z'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.save(self.payload(revision='2', enabled=True))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_model_profile_version SET region='other'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.save(self.payload(revision='2'))

    async def test_audit_failure_rolls_back_and_concurrent_revision_has_one_winner(self):
        original = ProviderDao.add

        async def fail_audit(db, model, **values):
            if model is HfAuditLog:
                raise RuntimeError('模拟审计存储失败')
            return await original(db, model, **values)

        with patch.object(ProviderDao, 'add', side_effect=fail_audit), self.assertRaises(RuntimeError):
            await self.save()
        async with self.sessions() as db:
            self.assertEqual((await RoutingService.get(db, self.owner, self.project_id))['revision'], '1')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_provider_config')), 0)
        results = await asyncio.gather(self.save(), self.save(), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, tuple) for value in results), 1)
        self.assertEqual(sum(isinstance(value, ServiceWarning) for value in results), 1)

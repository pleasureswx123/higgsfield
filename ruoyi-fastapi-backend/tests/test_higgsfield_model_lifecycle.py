"""模型状态竞争、配置不可变和审计原子性。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.model_vo import (
    ModelVersionCreate,
    ModelVariantCreate,
    ModelVersionPatch,
    ModelVersionAction,
    ModelVersionVerify,
)
from module_higgsfield.service.model_admin_service import ModelAdminService
from tests import test_higgsfield_models as models
from tests.test_higgsfield_model_capabilities import capability


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ModelLifecycleTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = models.ModelTests.cleanup_schema
    make_model = models.ModelTests.make_model

    async def asyncSetUp(self):
        await models.ModelTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'audit_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_16_audit.py'
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)
        model_id = await self.make_model()
        async with self.sessions() as db:
            result, _ = await ModelAdminService.create(
                db,
                self.owner,
                'version',
                ModelVersionCreate(gatewayAlias='test-v1', region='eva', capabilities=capability()),
                str(uuid4()),
                model_id,
            )
            self.version_id = int(result['data']['id'])

    async def act(self, action, payload, key=None):
        async with self.sessions() as db:
            return await ModelAdminService.mutate(db, self.owner, self.version_id, action, payload, key or str(uuid4()))

    async def add_variant(self):
        async with self.sessions() as db:
            await ModelAdminService.create(
                db, self.owner, 'variant', ModelVariantCreate(dimensions={}), str(uuid4()), self.version_id
            )

    async def test_lifecycle_replay_and_immutable_published_version(self):
        with self.assertRaises(ServiceWarning):
            await self.act('publish', ModelVersionAction(revision='1', reason='不允许跳过验证'))
        with self.assertRaises(ServiceWarning):
            await self.act(
                'verify', ModelVersionVerify(revision='1', reason='无规格不能验证', verificationRef='test-evidence')
            )
        await self.add_variant()
        verify = ModelVersionVerify(
            revision='2', reason='隔离测试中的人工审阅模拟', verificationRef='tests/evidence/model-v1'
        )
        key = str(uuid4())
        first, _ = await self.act('verify', verify, key)
        again, repeated = await self.act('verify', verify, key)
        self.assertTrue(repeated)
        self.assertEqual(first, again)
        with self.assertRaises(ServiceWarning):
            await self.act('edit', ModelVersionPatch(revision='3', gatewayAlias='overwritten'))
        published, _ = await self.act('publish', ModelVersionAction(revision='3', reason='测试发布'))
        self.assertEqual(published['data']['status'], 'published')
        disabled, _ = await self.act('disable', ModelVersionAction(revision='4', reason='测试停用'))
        self.assertEqual(disabled['data']['status'], 'disabled')
        with self.assertRaises(ServiceWarning):
            await self.act('publish', ModelVersionAction(revision='5', reason='不能直接重新发布'))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 3)
            self.assertEqual(await db.scalar(text('SELECT gateway_alias FROM hf_model_profile_version')), 'test-v1')

    async def test_edit_cas_and_audit_failure_roll_back_together(self):
        saved, _ = await self.act('edit', ModelVersionPatch(revision='1', gatewayAlias='test-v2'))
        self.assertEqual(saved['data']['revision'], '2')
        with self.assertRaises(ServiceWarning):
            await self.act('edit', ModelVersionPatch(revision='1', gatewayAlias='stale'))
        with patch(
            'module_higgsfield.service.model_admin_service.ModelDao.add',
            new=AsyncMock(side_effect=RuntimeError('模拟审计失败')),
        ):
            with self.assertRaises(RuntimeError):
                await self.act('disable', ModelVersionAction(revision='2', reason='应整体回滚'))
        async with self.sessions() as db:
            row = await ModelAdminService.get(db, self.owner, self.version_id)
            self.assertEqual(row['status'], 'draft')
            self.assertEqual(row['revision'], '2')
            self.assertEqual(row['gatewayAlias'], 'test-v2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)

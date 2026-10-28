"""后台模型登记、规范化规格和权限的隔离数据库验证。"""

import importlib.util
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.do.model_do import HfProviderConnection
from module_higgsfield.entity.vo.model_vo import ModelCreate, ModelVersionCreate, ModelVariantCreate
from module_higgsfield.service.model_admin_service import ModelAdminService
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_projects as projects
from tests.test_higgsfield_model_capabilities import capability


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ModelTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'models_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_13_models.py'
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)
        async with self.sessions() as db:
            row = await ModelDao.add(
                db,
                HfProviderConnection,
                connection_name='隔离测试连接',
                environment='test',
                status='0',
                revision=1,
                **WriteService.audit(self.owner),
            )
            self.connection_id = str(row.connection_id)
            await db.commit()

    async def make_model(self):
        async with self.sessions() as db:
            result, _ = await ModelAdminService.create(
                db,
                self.owner,
                'model',
                ModelCreate(connectionId=self.connection_id, code='image_test', displayName='测试模型', kind='image'),
                str(uuid4()),
            )
            return int(result['data']['id'])

    async def test_version_creation_replay_and_permission(self):
        model_id = await self.make_model()
        data = ModelVersionCreate(gatewayAlias='exact_alias', region='eva', capabilities=capability())
        key = str(uuid4())
        async with self.sessions() as db:
            first, _ = await ModelAdminService.create(db, self.owner, 'version', data, key, model_id)
        async with self.sessions() as db:
            replay, repeated = await ModelAdminService.create(db, self.owner, 'version', data, key, model_id)
            self.assertTrue(repeated)
            self.assertEqual(first, replay)
            self.assertEqual(first['data']['status'], 'draft')
            self.assertIsNone(first['data']['underlyingModelId'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_model_profile_version')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_api_idempotency_record WHERE api_prefix='/api/admin/v1'")), 2)
        async with self.sessions() as db:
            second, _ = await ModelAdminService.create(db, self.owner, 'version', data, str(uuid4()), model_id)
            self.assertEqual(second['data']['versionNo'], 2)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ModelAdminService.get(
                    db, SimpleNamespace(user=self.owner.user, permissions=['project:read']), int(first['data']['id'])
                )

    async def test_exact_variant_normalization_and_immutable_state(self):
        model_id = await self.make_model()
        config = capability().model_dump(by_alias=True)
        config['variantDimensions'] = {'duration': {'type': 'number', 'minimum': 1, 'maximum': 12}}
        async with self.sessions() as db:
            version, _ = await ModelAdminService.create(
                db,
                self.owner,
                'version',
                ModelVersionCreate(gatewayAlias='exact_alias', region='eva', capabilities=config),
                str(uuid4()),
                model_id,
            )
        version_id = int(version['data']['id'])
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ModelAdminService.create(
                    db, self.owner, 'variant', ModelVariantCreate(dimensions={}), str(uuid4()), version_id
                )
        async with self.sessions() as db:
            result, _ = await ModelAdminService.create(
                db, self.owner, 'variant', ModelVariantCreate(dimensions={'duration': 4.0}), str(uuid4()), version_id
            )
            self.assertEqual(result['data']['dimensions'], {'duration': 4})
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ModelAdminService.create(
                    db, self.owner, 'variant', ModelVariantCreate(dimensions={'duration': 4}), str(uuid4()), version_id
                )
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_model_profile_version SET status='2' WHERE model_version_id=:id"), {'id': version_id}
            )
            await db.commit()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ModelAdminService.create(
                    db, self.owner, 'variant', ModelVariantCreate(dimensions={'duration': 8}), str(uuid4()), version_id
                )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_model_variant')), 1)

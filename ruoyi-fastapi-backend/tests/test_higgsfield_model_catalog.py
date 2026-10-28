"""制作端目录不能通过后台权限绕过项目成员边界。"""

import importlib.util
import json
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.model_catalog_vo import ModelCatalogQuery
from module_higgsfield.entity.vo.draft_vo import DraftCreate
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.draft_service import DraftService
from tests import test_higgsfield_routing as routing
from tests.test_higgsfield_model_capabilities import capability


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CatalogTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = routing.RoutingTests.cleanup_schema

    async def asyncSetUp(self):
        await routing.RoutingTests.asyncSetUp(self)
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'generation:create','project' FROM hf_project_role WHERE code='owner'"
                )
            )
            await db.execute(
                text("UPDATE hf_model_profile_version SET status='2',capabilities=CAST(:cap AS jsonb)"),
                {'cap': json.dumps(capability().model_dump(by_alias=True))},
            )
            await db.execute(
                text(
                    "INSERT INTO hf_project_provider_config(project_id,model_id,account_id,status,priority,revision,create_time,update_time) VALUES (:p,:m,:a,'0',100,1,NOW(),NOW())"
                ),
                {'p': self.project_id, 'm': int(self.model_id), 'a': int(self.account_id)},
            )
            self.model_version_id = str(
                await db.scalar(text('SELECT model_version_id FROM hf_model_profile_version LIMIT 1'))
            )
            await db.commit()
        spec = importlib.util.spec_from_file_location(
            'catalog_draft_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_12_drafts.py'
        )
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)

    async def listing(self, user=None, **values):
        async with self.sessions() as db:
            return await ModelCatalogService.listing(
                db, user or self.owner, ModelCatalogQuery(projectId=str(self.project_id), kind='image', **values)
            )

    async def test_published_scope_projection_and_literal_search(self):
        result = await self.listing(pageSize=1)
        self.assertEqual(result.total, 1)
        self.assertFalse(result.rows[0]['availability']['available'])
        encoded = result.model_dump_json(by_alias=True)
        for key in ('accountId', 'connectionId', 'gatewayAlias', 'credentialId', 'apiKey', 'fingerprint'):
            self.assertNotIn(key, encoded)
        self.assertEqual((await self.listing(q='%')).total, 0)
        self.assertEqual((await self.listing(versionId=self.model_version_id)).total, 1)
        self.assertEqual((await self.listing(versionId='99999')).total, 0)
        with self.assertRaises(ServiceWarning):
            await self.listing(user=self.other)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_provider_config SET status='1'"))
            await db.commit()
        self.assertEqual((await self.listing()).total, 0)

    async def test_draft_parameters_are_authorized_and_validated(self):
        async def save(parameters, kind='image'):
            async with self.sessions() as db:
                return await DraftService.save(
                    db,
                    self.owner,
                    DraftCreate(
                        projectId=str(self.project_id),
                        kind=kind,
                        body={
                            'prompt': {'content': []},
                            'modelVersionId': self.model_version_id,
                            'parameters': parameters,
                        },
                    ),
                    str(uuid4()),
                )

        first, _ = await save({'duration': 6})
        self.assertEqual(first['data']['body']['parameters'], {'duration': 6})
        # 草稿允许未填写必填字段，执行预检必须另行要求完整。
        await save({})
        for params in ({'duration': True}, {'unknown': 'x'}, {'resolution': '1080p', 'duration': 6}):
            with self.assertRaises(ServiceWarning):
                await save(params)
        with self.assertRaises(ServiceWarning):
            await save({}, kind='video')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_model_profile_version SET status='3'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await save({})
        self.assertEqual((await self.listing()).total, 0)

"""连接白名单与配置不可变版本的隔离数据库验证。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.provider_vo import ConnectionCreate, ConnectionPatch
from module_higgsfield.service.provider_service import ProviderService
from tests import test_higgsfield_models as models


def config():
    return {
        'allowedHosts': ['example.com'],
        'bizId': 'op',
        'connectTimeoutSeconds': 10,
        'readTimeoutSeconds': 60,
        'operationTimeoutSeconds': 120,
        'taskTimeoutSeconds': 3600,
    }


def payload(**kwargs):
    return ConnectionCreate(
        **{
            'name': '测试连接',
            'environment': 'production',
            'baseUrl': 'http://example.com',
            'adapterVersion': 'videoplus-v1',
            'config': config(),
            **kwargs,
        }
    )


class ConnectionInputTests(unittest.TestCase):
    def test_address_normalization_and_secret_rejection(self):
        self.assertEqual(payload().base_url, 'http://example.com/')
        for url in (
            'https://user:secret@example.com',
            'https://example.com/?key=secret',
            'https://example.com/#fragment',
            'file:///secret',
            'https://example.com/%2e%2e/a',
            'https://other.example',
            'https://example.com/../a',
        ):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                payload(baseUrl=url)
        for change in (
            {'headers': {'Authorization': 'secret'}},
            {'apiKey': 'secret'},
            {'bizId': 'custom'},
            {'allowedHosts': ['*.example.com']},
            {'operationTimeoutSeconds': 1},
            {'connectTimeoutSeconds': True},
        ):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                payload(config={**config(), **change})


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = models.ModelTests.cleanup_schema

    async def asyncSetUp(self):
        await models.ModelTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'provider_version_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_14_provider_versions.py',
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)

    async def make(self, key=None):
        async with self.sessions() as db:
            return await ProviderService.save(db, self.owner, payload(), key or str(uuid4()))

    async def test_replay_and_version_preservation(self):
        key = str(uuid4())
        first, _ = await self.make(key)
        again, repeated = await self.make(key)
        self.assertTrue(repeated)
        self.assertEqual(first, again)
        connection = first['data']
        self.assertEqual(connection['status'], 'draft')
        old_version = connection['currentVersion']
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_provider_connection SET status='1' WHERE connection_id=:id"),
                {'id': int(connection['id'])},
            )
            await db.commit()
        async with self.sessions() as db:
            renamed, _ = await ProviderService.save(
                db, self.owner, ConnectionPatch(revision='1', name='新名称'), str(uuid4()), int(connection['id'])
            )
            self.assertEqual(renamed['data']['currentVersion']['id'], old_version['id'])
            self.assertEqual(renamed['data']['status'], 'active')
        async with self.sessions() as db:
            changed, _ = await ProviderService.save(
                db,
                self.owner,
                ConnectionPatch(revision='2', baseUrl='https://example.com/api'),
                str(uuid4()),
                int(connection['id']),
            )
            self.assertEqual(changed['data']['status'], 'draft')
            self.assertEqual(changed['data']['currentVersion']['versionNo'], 2)
            self.assertNotEqual(changed['data']['currentVersion']['configHash'], old_version['configHash'])
            self.assertEqual(
                await db.scalar(
                    text('SELECT base_url FROM hf_provider_connection_version WHERE connection_version_id=:id'),
                    {'id': int(old_version['id'])},
                ),
                'http://example.com/',
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_connection_version')), 2)

    async def test_conflicts_leave_current_config_unchanged(self):
        first, _ = await self.make()
        connection_id = int(first['data']['id'])
        with self.assertRaises(ServiceWarning):
            await self.make()
        for update in (
            ConnectionPatch(revision='999', name='冲突'),
            ConnectionPatch(revision='1', baseUrl='https://other.example/'),
        ):
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning):
                    await ProviderService.save(db, self.owner, update, str(uuid4()), connection_id)
        async with self.sessions() as db:
            current = await ProviderService.get(db, self.owner, connection_id)
            self.assertEqual(current['revision'], '1')
            self.assertEqual(current['currentVersion']['id'], first['data']['currentVersion']['id'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_connection_version')), 1)

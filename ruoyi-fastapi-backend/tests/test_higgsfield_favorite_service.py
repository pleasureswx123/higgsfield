"""收藏真实授权、事务回滚与撤权后的安全投影。"""
import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.vo.favorite_vo import FavoriteCreate, FavoriteQuery
from module_higgsfield.service.favorite_service import FavoriteService as Service
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.output_read_service import OutputReadService
from tests import test_higgsfield_element_service as elements
from tests import test_higgsfield_job_storage as storage


class FavoriteProjectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_asset_projection_uses_authorized_reader_and_excludes_file_details(self):
        user, db = object(), object()
        with (patch.object(AssetService, 'get', AsyncMock(return_value={'name': '参考图', 'mediaType': 'image',
                'revision': '2', 'file': {'storage_key': '不可泄露'}})) as read,
             patch.object(AssetDao, 'project_id', AsyncMock(return_value=12))):
            result = await Service.source(db, user, 'asset', 33)
            read.assert_awaited_once_with(db, user, 33)
            self.assertEqual(result, {'name': '参考图', 'mediaType': 'image', 'revision': '2', 'projectId': '12'})

    async def test_output_projection_reuses_object_authorization_without_source_urls(self):
        user, db = object(), object()
        output = SimpleNamespace(ordinal=0, job_id=9007199254740993, kind='image', revision=2,
                                 source_url_ciphertext='不可泄露')
        with patch.object(OutputReadService, 'authorized', AsyncMock(return_value=(output, set()))) as read:
            result = await Service.source(db, user, 'output', 44)
            read.assert_awaited_once_with(db, user, 44)
            self.assertEqual(result['jobId'], '9007199254740993')
            self.assertNotIn('source_url_ciphertext', result)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class FavoriteServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = elements.ElementServiceTests.cleanup_schema
    create = elements.ElementServiceTests.create
    make_element = elements.ElementServiceTests.make_element
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await elements.ElementServiceTests.asyncSetUp(self)
        for name in ('20261027_16_audit.py', '20261028_67_favorites.py'):
            spec = importlib.util.spec_from_file_location('favorite_service_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.element = (await self.make_element())['element']['id']
        self.payload = FavoriteCreate(target={'elementId': self.element})

    async def save(self, key=None):
        async with self.sessions() as db:
            return await Service.create(db, self.owner, self.payload, key or str(uuid4()))

    async def test_read_permission_revocation_hides_source_and_blocks_replay_but_allows_cancel(self):
        key = str(uuid4())
        first, _ = await self.save(key)
        identity = int(first['data']['id'])
        repeated, replayed = await self.save(key)
        self.assertTrue(replayed)
        self.assertEqual(first, repeated)
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery())
            self.assertEqual(page.rows[0]['source']['name'], '主角')
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='element:read'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.save(key)
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery())
            self.assertEqual(page.total, 1)
            self.assertFalse(page.rows[0]['available'])
            self.assertNotIn('source', page.rows[0])
            await Service.cancel(db, self.owner, identity, str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual((await Service.listing(db, self.owner, FavoriteQuery())).total, 0)

    async def test_concurrent_create_and_restore_keep_single_identity(self):
        results = await asyncio.gather(self.save(), self.save())
        identities = {item[0]['data']['id'] for item in results}
        self.assertEqual(len(identities), 1)
        identity = int(next(iter(identities)))
        async with self.sessions() as db:
            await Service.cancel(db, self.owner, identity)
        restored, _ = await self.save()
        self.assertEqual(restored['data']['id'], str(identity))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_favorite')), 1)
            await db.execute(text("UPDATE hf_element SET del_flag='2' WHERE element_id=:id"), {'id': int(self.element)})
            await db.commit()
        async with self.sessions() as db:
            self.assertFalse((await Service.listing(db, self.owner, FavoriteQuery())).rows[0]['available'])
        with self.assertRaises(ServiceWarning):
            await self.save()

    async def test_audit_failure_rolls_back_and_other_user_cannot_cancel(self):
        with patch.object(AssetDao, 'add', side_effect=RuntimeError('模拟审计失败')):
            with self.assertRaises(RuntimeError):
                await self.save()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_favorite')), 0)
        result, _ = await self.save()
        identity = int(result['data']['id'])
        other = SimpleNamespace(user=SimpleNamespace(user_id=999, user_name='other'), permissions=['*:*:*'])
        async with self.sessions() as db:
            self.assertEqual((await Service.listing(db, other, FavoriteQuery())).total, 0)
            with self.assertRaises(ServiceWarning):
                await Service.cancel(db, other, identity)
        with patch.object(AssetDao, 'add', side_effect=RuntimeError('模拟审计失败')):
            async with self.sessions() as db:
                with self.assertRaises(RuntimeError):
                    await Service.cancel(db, self.owner, identity)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT del_flag FROM hf_favorite')), '0')

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class FavoriteOutputTests(unittest.IsolatedAsyncioTestCase):
    from tests.test_higgsfield_output_read import OutputReadTests as Fixture
    cleanup_schema = Fixture.cleanup_schema
    migrate = Fixture.migrate
    job = Fixture.job
    output = Fixture.output
    create = Fixture.create

    async def asyncSetUp(self):
        await self.Fixture.asyncSetUp(self)
        for name in ('20261027_16_audit.py', '20261028_67_favorites.py'):
            spec = importlib.util.spec_from_file_location('favorite_output_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')

    async def test_output_favorite_needs_only_output_read_and_revocation_hides_it(self):
        payload = FavoriteCreate(target={'outputId': str(self.identity)})
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='generation:read'"))
            await db.commit()
            saved, _ = await Service.create(db, self.owner, payload, str(uuid4()))
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery(kind='output'))
            self.assertEqual(page.total, 1)
            self.assertTrue(page.rows[0]['available'])
            self.assertNotIn('encrypted-test-source', str(page.rows))
            self.assertNotIn('previewUrl', page.rows[0]['source'])
            output = await OutputReadService.get(db, self.owner, self.identity)
            self.assertEqual(output['id'], str(self.identity))
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery(kind='output'))
            self.assertFalse(page.rows[0]['available'])
            self.assertNotIn('source', page.rows[0])
            with self.assertRaises(PermissionException):
                await OutputReadService.get(db, self.owner, self.identity)
            await Service.cancel(db, self.owner, int(saved['data']['id']), str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual((await Service.listing(db, self.owner, FavoriteQuery())).total, 0)

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class FavoriteAssetTests(unittest.IsolatedAsyncioTestCase):
    from tests.test_higgsfield_assets import AssetDatabaseTests as Fixture
    cleanup_schema = Fixture.cleanup_schema
    create = Fixture.create
    new_upload = Fixture.new_upload
    send_part = Fixture.send_part
    ready_upload = Fixture.ready_upload
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await self.Fixture.asyncSetUp(self)
        for name in ('20261027_16_audit.py', '20261028_67_favorites.py'):
            spec = importlib.util.spec_from_file_location('favorite_asset_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')

    async def test_uploaded_asset_favorite_reauthorizes_after_member_disabled(self):
        from module_higgsfield.entity.vo.asset_vo import AssetCreate
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            bound, _ = await AssetService.bind(db, self.owner,
                AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='收藏测试素材'), str(uuid4()))
            payload = FavoriteCreate(target={'assetId': bound['data']['id']})
            saved, _ = await Service.create(db, self.owner, payload, str(uuid4()))
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery(kind='asset'))
            self.assertEqual(page.rows[0]['source']['name'], '收藏测试素材')
            self.assertEqual(page.rows[0]['source']['projectId'], self.project_id)
            self.assertNotIn('file', page.rows[0]['source'])
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
        async with self.sessions() as db:
            page = await Service.listing(db, self.owner, FavoriteQuery(kind='asset'))
            self.assertEqual(page.total, 1)
            self.assertFalse(page.rows[0]['available'])
            self.assertNotIn('source', page.rows[0])
            await Service.cancel(db, self.owner, int(saved['data']['id']), str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual((await Service.listing(db, self.owner, FavoriteQuery())).total, 0)

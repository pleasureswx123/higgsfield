"""页面偏好白名单、真实迁移与并发修订验证。"""
import asyncio
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.view_preference_vo import normalize_settings, ViewPreferenceUpdate
from module_higgsfield.entity.do.view_preference_do import HfUserViewPreference
from module_higgsfield.service.view_preference_service import ViewPreferenceService as Service
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.project_preference_service import PreferenceService
from tests import test_higgsfield_projects as projects
from tests import test_higgsfield_job_storage as storage


class ViewInputTests(unittest.TestCase):
    def test_element_source_filter_default_and_whitelist(self):
        self.assertEqual(normalize_settings('elements', {})['mineFilter'], 'all')
        for source in ('all', 'created', 'favorites'):
            self.assertEqual(normalize_settings('elements', {'mineFilter': source})['mineFilter'], source)
        for source in ('project', '', None, True):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                normalize_settings('elements', {'mineFilter': source})


    def test_library_dates_preserve_calendar_days_and_reject_invalid_ranges(self):
        self.assertIsNone(normalize_settings('library', {})['dates'])
        self.assertIsNone(normalize_settings('library', {'dates': None})['dates'])
        dates = ['2024-02-29', '2024-03-01']
        self.assertEqual(normalize_settings('library', {'dates': dates})['dates'], dates)
        self.assertEqual(normalize_settings('library', {'dates': ['2024-02-29'] * 2})['dates'], ['2024-02-29'] * 2)
        for value in ([], ['2024-02-29'], ['2024-01-01'] * 3, ['2025-02-29', '2025-03-01'],
                      ['2024-03-02', '2024-03-01'], ['20240101', '20240102'], [1, 2],
                      ['2024-01-01T00:00:00+08:00', '2024-01-02']):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_settings('library', {'dates': value})

    def test_whitelist_and_distinct_layouts(self):
        self.assertFalse(normalize_settings('library', {})['includeDescendants'])
        self.assertTrue(normalize_settings('library', {'includeDescendants': True})['includeDescendants'])
        with self.assertRaises(ValidationError):
            normalize_settings('library', {'includeDescendants': 'true'})
        self.assertEqual(normalize_settings('library', {'layout': 'masonry', 'cardSize': 8})['cardSize'], 8)
        self.assertEqual(normalize_settings('elements', {'layout': 'board'})['layout'], 'board')
        for key, value in [('library', {'layout': 'board'}), ('elements', {'layout': 'masonry'}),
                           ('library', {'token': 'secret'}), ('library', {'cardSize': True}),
                           ('library', {'cardSize': 9}), ('library', {'splitByDate': 'true'}),
                           ('library', {'pinnedFolderIds': ['1', '1']}), ('projects', {'collectionId': 1})]:
            with self.subTest(key=key, value=value), self.assertRaises(ValidationError):
                normalize_settings(key, value)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ViewPreferenceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    create = projects.ProjectDatabaseTests.create
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_73_view_preferences.py'
        spec = importlib.util.spec_from_file_location('view_preference_migration', path)
        self.migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.migration)
        # 基础项目夹具已执行真实 73 迁移。
        result, _ = await self.create(); self.project_id = int(result['data']['id'])

    async def put(self, key='projects', settings=None, revision='0', project_id=None, actor=None, request_key=None):
        async with self.sessions() as db:
            return await Service.put(db, actor or self.owner, key,
                ViewPreferenceUpdate(revision=revision, projectId=str(project_id) if project_id else None, settings=settings or {}), request_key or str(uuid4()))

    async def test_element_source_filter_persists_and_is_user_scoped(self):
        request_key = str(uuid4())
        settings = {'mineFilter': 'favorites', 'layout': 'table'}
        await self.put('elements', settings, request_key=request_key)
        self.assertTrue((await self.put('elements', settings, request_key=request_key))[1])
        async with self.sessions() as db:
            saved = await Service.get(db, self.owner, 'elements')
            self.assertEqual(saved['settings']['mineFilter'], 'favorites')
            self.assertEqual(saved['settings']['layout'], 'table')
            self.assertEqual((await Service.get(db, self.other, 'elements'))['settings']['mineFilter'], 'all')
        await self.put('elements', {'mineFilter': 'created'}, revision=saved['revision'])
        async with self.sessions() as db:
            self.assertEqual((await Service.get(db, self.owner, 'elements'))['settings']['mineFilter'], 'created')

    async def test_concurrent_first_write_and_scope_revoke(self):
        async with self.sessions() as db:
            self.assertEqual((await Service.get(db, self.owner, 'projects'))['revision'], '0')
        outcomes = await asyncio.gather(self.put(settings={'hidden': True}), self.put(settings={'pinned': True}), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, tuple) for item in outcomes), 1)
        self.assertEqual(sum(isinstance(item, ServiceWarning) for item in outcomes), 1)
        async with self.sessions() as db:
            self.assertEqual((await Service.get(db, self.other, 'projects'))['revision'], '0')
        request_key = str(uuid4())
        saved = {'layout': 'masonry', 'dates': ['2024-02-29', '2024-03-01']}
        await self.put('library', saved, project_id=self.project_id, request_key=request_key)
        self.assertTrue((await self.put('library', saved, project_id=self.project_id, request_key=request_key))[1])
        async with self.sessions() as db:
            self.assertEqual((await Service.get(db, self.owner, 'library', self.project_id))['settings']['dates'], saved['dates'])
        with self.assertRaises(ServiceWarning):
            await self.put('library', project_id=self.project_id, actor=self.other)
        with self.assertRaises(ServiceWarning):
            await self.put('projects', project_id=self.project_id)
        with self.assertRaises(ServiceWarning):
            await self.put('library', {'arbitrary': 'secret'})
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_member SET status='1'")); await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.put('library', {'layout': 'masonry'}, project_id=self.project_id, request_key=request_key)

    async def test_real_storage_null_uniqueness_and_comments(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            for scope in (None, self.project_id):
                db.add(HfUserViewPreference(user_id=1, view_key='library', project_id=scope, **audit))
            await db.flush()
            for fields in ({'project_id': None}, {'project_id': self.project_id},
                           {'user_id': 2, 'revision': 0}, {'user_id': 2, 'settings': []}, {'user_id': 2, 'view_key': 'unknown'}):
                with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfUserViewPreference(**(dict(user_id=1, view_key='library') | fields), **audit))
                        await db.flush()
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_user_view_preference'::regclass AND contype='f'")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_user_view_preference'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertTrue(await db.scalar(text("SELECT obj_description('hf_user_view_preference'::regclass,'pg_class')")))
            await db.rollback()
        with self.assertRaises(RuntimeError):
            await self.migrate('downgrade')

    async def test_collection_delete_clears_saved_view_and_serializes_save(self):
        async with self.sessions() as db:
            result, _ = await PreferenceService.mutate_collection(db, self.owner, 'create', {'name': '分组'}, str(uuid4()))
            identity = result['data']['id']
        await self.put(settings={'collectionId': identity, 'pinned': True})
        await self.put(settings={'hidden': True}, actor=self.other)
        async def remove():
            async with self.sessions() as db:
                return await PreferenceService.mutate_collection(db, self.owner, 'delete', {'revision': '1'}, str(uuid4()), int(identity))
        outcomes = await asyncio.gather(remove(), self.put(settings={'collectionId': identity, 'hidden': True}, revision='1'), return_exceptions=True)
        self.assertIsInstance(outcomes[0], tuple)
        self.assertTrue(isinstance(outcomes[1], (tuple, ServiceWarning)))
        async with self.sessions() as db:
            current = await Service.get(db, self.owner, 'projects')
            self.assertIsNone(current['settings']['collectionId'])
            self.assertGreater(int(current['revision']), 1)
            other = await Service.get(db, self.other, 'projects')
            self.assertEqual(other['revision'], '1'); self.assertTrue(other['settings']['hidden'])
        with self.assertRaises(ServiceWarning):
            await self.put(settings={'pinned': False}, revision='1')

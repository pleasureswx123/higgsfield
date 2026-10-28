"""真实数据库验证个人导航权限、幂等和并发。"""
import asyncio
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.project_preference_vo import CollectionQuery
from module_higgsfield.service.project_preference_service import PreferenceService as Service
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.entity.vo.project_vo import ProjectQuery
from tests import test_higgsfield_project_preference_storage as storage
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PreferenceServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.PreferenceStorageTests.cleanup_schema
    migrate = storage.PreferenceStorageTests.migrate
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await storage.PreferenceStorageTests.asyncSetUp(self)
        result, _ = await self.create()
        self.project_id = int(result['data']['id'])

    async def collection(self, action='create', payload=None, identity=None, user=None, key=None):
        async with self.sessions() as db:
            return await Service.mutate_collection(db, user or self.owner, action,
                payload or {'name': '制作'}, key or str(uuid4()), identity)

    async def preference(self, payload, user=None, key=None):
        async with self.sessions() as db:
            return await Service.put_preference(db, user or self.owner, self.project_id, payload, key or str(uuid4()))

    async def test_owner_isolation_replay_and_revision(self):
        result, _ = await self.collection()
        identity = int(result['data']['id'])
        async with self.sessions() as db:
            self.assertEqual((await Service.list_collections(db, self.other, CollectionQuery())).total, 0)
        with self.assertRaises(ServiceWarning):
            await self.collection('update', {'revision': '1', 'name': '越权'}, identity, self.other)
        with self.assertRaises(ServiceWarning):
            await self.preference({'revision': '0', 'isPinned': True}, self.other)
        foreign, _ = await self.collection(user=self.other)
        with self.assertRaises(ServiceWarning):
            await self.preference({'revision': '0', 'collectionId': foreign['data']['id']})
        key = str(uuid4()); payload = {'revision': '0', 'isPinned': True, 'collectionId': str(identity)}
        first = await self.preference(payload, key=key)
        self.assertEqual(first[0]['data']['revision'], '1')
        self.assertTrue((await self.preference(payload, key=key))[1])
        with self.assertRaises(ServiceWarning):
            await self.preference(payload)
        second, _ = await self.preference({'revision': '1', 'isHidden': True})
        self.assertTrue(second['data']['isPinned']); self.assertEqual(second['data']['collectionId'], str(identity))
        delete_key = str(uuid4())
        await self.collection('delete', {'revision': '1'}, identity, key=delete_key)
        self.assertTrue((await self.collection('delete', {'revision': '1'}, identity, key=delete_key))[1])
        async with self.sessions() as db:
            value = await Service.get_preference(db, self.owner, self.project_id)
            self.assertIsNone(value['collectionId']); self.assertEqual(value['revision'], '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_project_member WHERE status='0'")), 1)

    async def test_concurrent_delete_move_and_readonly(self):
        result, _ = await self.collection(); identity = int(result['data']['id'])
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project SET status='2', archived_time=now()")); await db.commit()
        await self.preference({'revision': '0', 'isPinned': True})
        results = await asyncio.gather(
            self.collection('delete', {'revision': '1'}, identity),
            self.preference({'revision': '1', 'collectionId': str(identity)}), return_exceptions=True)
        self.assertIsInstance(results[0], tuple)
        self.assertTrue(isinstance(results[1], (tuple, ServiceWarning)))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_collection')), 0)
            self.assertIsNone(await db.scalar(text('SELECT collection_id FROM hf_user_project_preference')))
        key = str(uuid4()); payload = {'revision': (await self.read())['revision'], 'isHidden': True}
        await self.preference(payload, key=key)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_member SET status='1'")); await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.preference(payload, key=key)

    async def read(self):
        async with self.sessions() as db:
            return await Service.get_preference(db, self.owner, self.project_id)

    async def test_list_filter_counts_order_and_member_boundary(self):
        second, _ = await self.create(name='第二项目')
        second_id = int(second['data']['id'])
        collection, _ = await self.collection()
        identity = collection['data']['id']
        await self.preference({'revision': '0', 'isPinned': True, 'collectionId': identity})
        async with self.sessions() as db:
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery(pageSize=1))
            self.assertEqual(page.total, 2); self.assertTrue(page.has_next)
            self.assertEqual(page.rows[0].id, str(self.project_id))
            self.assertEqual(page.rows[0].preference.collection_id, identity)
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery(collectionId=identity))
            self.assertEqual(page.total, 1)
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery(pinned=False))
            self.assertEqual([row.id for row in page.rows], [str(second_id)])
        await self.preference({'revision': '1', 'isHidden': True})
        async with self.sessions() as db:
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery())
            self.assertEqual(page.total, 1); self.assertEqual(page.rows[0].id, str(second_id))
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery(hidden=True, pinned=True))
            self.assertEqual(page.total, 1); self.assertTrue(page.rows[0].preference.is_hidden)
            # 隐藏只影响列表导航，直接读取仍遵守原项目成员权限。
            self.assertEqual((await ProjectService.get_project(db, self.owner, self.project_id)).id, str(self.project_id))
            page = await ProjectService.list_projects(db, self.other, ProjectQuery(hidden=True, collectionId=identity))
            self.assertEqual(page.total, 0)
            await db.execute(text('UPDATE hf_project_member SET status=\'1\' WHERE project_id=:id'), {'id': self.project_id})
            await db.commit()
            page = await ProjectService.list_projects(db, self.owner, ProjectQuery(hidden=True))
            self.assertEqual(page.total, 0)

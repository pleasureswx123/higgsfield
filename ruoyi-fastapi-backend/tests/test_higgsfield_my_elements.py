"""我的元素按本人创建或收藏聚合，收藏不突破项目和对象权限。"""
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from module_higgsfield.entity.vo.element_vo import ElementQuery
from module_higgsfield.entity.vo.favorite_vo import FavoriteCreate
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.favorite_service import FavoriteService
from tests import test_higgsfield_favorite_service as favorites


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class MyElementsTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = favorites.FavoriteServiceTests.cleanup_schema
    create = favorites.FavoriteServiceTests.create
    make_element = favorites.FavoriteServiceTests.make_element
    migrate = favorites.FavoriteServiceTests.migrate
    asyncSetUp = favorites.FavoriteServiceTests.asyncSetUp

    async def listing(self, **params):
        async with self.sessions() as db:
            return await ElementService.listing(db, self.owner, ElementQuery(scope='mine', **params))

    async def test_created_or_favorited_union_is_scoped_before_pagination(self):
        shared = (await self.make_element(alias='shared', name='收藏元素'))['element']['id']
        hidden = (await self.make_element(alias='hidden', name='未收藏元素'))['element']['id']
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_element SET create_user_id=2 WHERE element_id IN (:shared,:hidden)'),
                             {'shared': int(shared), 'hidden': int(hidden)})
            await db.commit()
        self.assertEqual((await self.listing()).total, 1)
        async with self.sessions() as db:
            for identity in (self.element, shared):
                await FavoriteService.create(db, self.owner, FavoriteCreate(target={'elementId': identity}), str(uuid4()))
        created = await self.listing(mineFilter='created')
        self.assertEqual([row['id'] for row in created.rows], [self.element])
        favorited = await self.listing(mineFilter='favorites', pageSize=1)
        self.assertEqual(favorited.total, 2)
        self.assertTrue(favorited.has_next)
        favorite_second = await self.listing(mineFilter='favorites', pageSize=1, pageNum=2)
        self.assertEqual({favorited.rows[0]['id'], favorite_second.rows[0]['id']}, {self.element, shared})
        self.assertEqual((await self.listing(mineFilter='created', q='收藏元素')).total, 0)
        page = await self.listing(pageSize=1)
        self.assertEqual(page.total, 2); self.assertTrue(page.has_next)
        second = await self.listing(pageSize=1, pageNum=2)
        self.assertEqual({page.rows[0]['id'], second.rows[0]['id']}, {self.element, shared})
        self.assertEqual((await self.listing(q='收藏元素')).total, 1)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_favorite SET del_flag='2' WHERE element_id=:id"), {'id': int(shared)})
            await db.commit()
        self.assertEqual((await self.listing()).total, 1)
        self.assertEqual((await self.listing(mineFilter='favorites')).total, 1)
        async with self.sessions() as db:
            await FavoriteService.create(db, self.owner, FavoriteCreate(target={'elementId': shared}), str(uuid4()))
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='element:read'"))
            await db.commit()
        self.assertEqual((await self.listing()).total, 1)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_member SET status='1' WHERE user_id=1"))
            await db.commit()
        self.assertEqual((await self.listing()).total, 0)
        self.assertEqual((await self.listing(mineFilter='favorites')).total, 0)
        self.assertEqual((await self.listing(mineFilter='created')).total, 0)


class MyElementQueryTests(unittest.TestCase):
    def test_source_filter_is_explicit_and_restricted_to_mine(self):
        self.assertEqual(ElementQuery(scope='mine').mine_filter, 'all')
        self.assertEqual(ElementQuery(scope='mine', mineFilter='favorites').mine_filter, 'favorites')
        with self.assertRaises(ValueError):
            ElementQuery(scope='project', projectId='1', mineFilter='created')
        with self.assertRaises(ValueError):
            ElementQuery(scope='mine', mineFilter='unknown')

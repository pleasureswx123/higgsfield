"""收藏真实迁移的目标互斥、去重、用户隔离及逻辑删除约束。"""
import importlib.util
import os
from pathlib import Path
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from module_higgsfield.entity.do.favorite_do import HfFavorite
from module_higgsfield.entity.vo.favorite_vo import FavoriteCreate
from module_higgsfield.entity.vo.favorite_vo import FavoriteQuery
from module_higgsfield.dao.favorite_dao import FavoriteDao
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage


class FavoriteInputTests(unittest.TestCase):
    def test_one_target_and_string_identity(self):
        valid = FavoriteCreate(target={'elementId': '9007199254740993'})
        self.assertEqual(valid.target.element_id, '9007199254740993')
        for payload in [{'target': {}}, {'target': {'elementId': '1', 'assetId': '2'}},
                        {'target': {'elementId': 1}}, {'target': {'assetId': '0'}},
                        {'target': {'outputId': '1'}, 'userId': '2'}]:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                FavoriteCreate.model_validate(payload)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class FavoriteStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('favorites',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_67_favorites.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_uniqueness_target_constraints_and_chinese_comments(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            favorite = HfFavorite(user_id=1, element_id=9007199254740993, **audit)
            db.add(favorite)
            await db.flush()
            identity = favorite.favorite_id
            favorite.del_flag = '2'
            await db.flush()
            # 取消后也不创建第二身份，再收藏必须恢复已有关系。
            for target in [{'element_id': 9007199254740993}, {}, {'element_id': 1, 'asset_id': 1},
                           {'asset_id': 0}, {'output_id': -1}, {'asset_id': 2, 'del_flag': '1'}]:
                with self.subTest(target=target), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfFavorite(user_id=1, **target, **audit))
                        await db.flush()
            favorite.del_flag = '0'
            db.add_all([HfFavorite(user_id=2, element_id=9007199254740993, **audit),
                        HfFavorite(user_id=1, asset_id=9007199254740993, **audit),
                        HfFavorite(user_id=1, output_id=9007199254740993, **audit)])
            await db.flush()
            self.assertEqual(favorite.favorite_id, identity)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_favorite')), 4)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_favorite'::regclass AND contype='f'")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_favorite'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertTrue(await db.scalar(text("SELECT obj_description('hf_favorite'::regclass,'pg_class')")))
            await db.rollback()

    async def test_dao_restore_keeps_identity_and_cannot_cancel_other_users(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            first = await FavoriteDao.save(db, 1, 'element', 99, audit)
            identity = first.favorite_id
            other = await FavoriteDao.save(db, 2, 'element', 99, audit)
            self.assertIsNone(await FavoriteDao.cancel(db, 1, other.favorite_id, audit))
            await FavoriteDao.cancel(db, 1, identity, audit)
            self.assertEqual((await FavoriteDao.page(db, 1, FavoriteQuery()))[1], 0)
            restored = await FavoriteDao.save(db, 1, 'element', 99, audit)
            self.assertEqual(restored.favorite_id, identity)
            self.assertEqual(restored.del_flag, '0')
            await FavoriteDao.save(db, 1, 'asset', 99, audit)
            rows, count = await FavoriteDao.page(db, 1, FavoriteQuery(kind='element', pageSize=1))
            self.assertEqual(count, 1)
            self.assertEqual([item.favorite_id for item in rows], [identity])
            await db.commit()

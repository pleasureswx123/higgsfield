"""素材活动筛选从版本来源及本人收藏取证。"""
import importlib.util
import os
import unittest
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
from pydantic import ValidationError
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry, HfUploadBinding
from module_higgsfield.entity.do.favorite_do import HfFavorite
from module_higgsfield.entity.do.folder_do import HfFolder
from module_higgsfield.entity.vo.asset_vo import LibraryQuery
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_assets as assets
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class LibraryActivityTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('activity_favorites', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_67_favorites.py')
        self.migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        self.ids = []
        async with self.sessions() as db:
            self.space_id = await db.scalar(text('SELECT space_id FROM hf_asset_space LIMIT 1'))
            audit = WriteService.audit(self.owner)
            versions = []
            for name in ('上传', '生成', '复制生成', '无来源'):
                row = HfAsset(space_id=self.space_id, asset_name=name, media_type='image', create_user_id=1, **audit)
                db.add(row); await db.flush(); self.ids.append(row.asset_id)
                version = HfAssetVersion(asset_id=row.asset_id, version_no=1, file_id=1, create_user_id=1, **audit)
                if name == '生成': version.source_output_id = 99
                if name == '复制生成': version.source_asset_version_id = versions[1].version_id
                db.add(version); await db.flush(); versions.append(version)
                row.current_version_id = version.version_id
                db.add(HfFolderEntry(space_id=self.space_id, asset_id=row.asset_id, **audit))
            db.add(HfUploadBinding(session_id=1, bound_by=1, asset_version_id=versions[0].version_id, **audit))
            db.add_all([HfFavorite(user_id=1, asset_id=self.ids[1], **audit),
                        HfFavorite(user_id=2, asset_id=self.ids[2], **audit),
                        HfFavorite(user_id=1, asset_id=self.ids[0], del_flag='2', **audit)])
            await db.commit()

    async def test_origin_personal_favorite_and_pagination(self):
        async with self.sessions() as db:
            for activity, expected, actor in [('uploaded', [self.ids[0]], 1), ('generated', self.ids[1:3], 1),
                                              ('liked', [self.ids[1]], 1), ('liked', [self.ids[2]], 2)]:
                rows, count = await AssetDao.library(db, self.space_id, LibraryQuery(activity=activity), actor)
                self.assertEqual(count, len(expected)); self.assertEqual({row[0].asset_id for row in rows}, set(expected))
            rows, count = await AssetDao.library(db, self.space_id, LibraryQuery(activity='generated', pageSize=1), 1)
            self.assertEqual(count, 2); self.assertEqual(len(rows), 1)
            rows, count = await AssetDao.library(db, self.space_id, LibraryQuery(activity='generated', q='复制'), 1)
            self.assertEqual(count, 1); self.assertEqual(rows[0][0].asset_id, self.ids[2])
            await db.execute(text("UPDATE hf_asset SET del_flag='2' WHERE asset_id=:id"), {'id': self.ids[1]})
            rows, count = await AssetDao.library(db, self.space_id, LibraryQuery(activity='liked'), 1)
            self.assertEqual(count, 0)

    async def test_descendant_scope_intersects_filters_before_paging(self):
        async with self.sessions() as db:
            root = HfFolder(space_id=self.space_id, folder_name='父', normalized_name='父')
            other = HfFolder(space_id=self.space_id, folder_name='旁支', normalized_name='旁支')
            db.add_all([root, other]); await db.flush()
            child = HfFolder(space_id=self.space_id, parent_id=root.folder_id, folder_name='子', normalized_name='子')
            db.add(child); await db.flush()
            for identity, folder in zip(self.ids, [None, root.folder_id, child.folder_id, other.folder_id]):
                await db.execute(text('UPDATE hf_folder_entry SET folder_id=:folder WHERE asset_id=:id'), {'folder': folder, 'id': identity})
            rows, count = await AssetDao.library(db, self.space_id, LibraryQuery(), 1)
            self.assertEqual(count, 1); self.assertEqual(rows[0][0].asset_id, self.ids[0])
            _, count = await AssetDao.library(db, self.space_id, LibraryQuery(includeDescendants=True), 1)
            self.assertEqual(count, 4)
            query = LibraryQuery(folderId=str(root.folder_id), includeDescendants=True, pageSize=1)
            first, count = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(count, 2); query.page_num = 2
            second, count = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(count, 2); self.assertNotEqual(first[0][0].asset_id, second[0][0].asset_id)
            query.page_num = 1; query.activity = 'liked'
            rows, count = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(count, 1); self.assertEqual(rows[0][0].asset_id, self.ids[1])
            query.activity = None; query.include_descendants = False
            rows, count = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(count, 1); self.assertEqual(rows[0][0].asset_id, self.ids[1])

    async def test_creation_window_is_left_closed_right_open_before_paging(self):
        async with self.sessions() as db:
            for identity, instant in zip(self.ids, ['2026-10-27T15:59:59Z', '2026-10-27T16:00:00Z', '2026-10-28T15:59:59Z', '2026-10-28T16:00:00Z']):
                await db.execute(text('UPDATE hf_asset SET create_time=CAST(:instant AS timestamptz) WHERE asset_id=:id'), {'instant': datetime.fromisoformat(instant), 'id': identity})
            query = LibraryQuery.model_validate({'from': '2026-10-28T00:00:00+08:00', 'to': '2026-10-29T00:00:00+08:00', 'pageSize': 1})
            rows, count = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(count, 2); self.assertEqual(len(rows), 1)
            query.page_num = 2
            other, total = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(total, 2)
            self.assertEqual({rows[0][0].asset_id, other[0][0].asset_id}, set(self.ids[1:3]))
            query.activity = 'liked'; query.page_num = 1
            liked, total = await AssetDao.library(db, self.space_id, query, 1)
            self.assertEqual(total, 1); self.assertEqual(liked[0][0].asset_id, self.ids[1])
        for values in [{'from': '2026-10-28T00:00:00'}, {'from': '2026-10-29T00:00:00Z', 'to': '2026-10-28T00:00:00Z'}, {'from': '2026-10-28T00:00:00Z', 'to': '2026-10-28T00:00:00Z'}]:
            with self.assertRaises(ValidationError): LibraryQuery.model_validate(values)

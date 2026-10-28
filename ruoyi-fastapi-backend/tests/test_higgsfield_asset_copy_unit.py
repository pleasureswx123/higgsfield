"""单素材复制复用目录复制规则，校验独立身份、来源及权限。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.folder_content_service import FolderContentService
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService

class AssetCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_keeps_original_and_references_archived_version(self):
        entry = NS(entry_id=7, asset_id=8, folder_id=2, order_num=0)
        source = NS(asset_id=8, space_id=1, del_flag='0', create_user_id=4,
                    current_version_id=9, asset_name='图片', media_type='image')
        version = NS(file_id=10, version_id=9, media_metadata={'width': 100})
        created = []
        user = NS(user=NS(user_id=4))
        # 各实体只补充自己的主键。
        async def insert(db, model, **fields):
            created.append((model.__name__, fields))
            key = {'HfAsset': 'asset_id', 'HfAssetVersion': 'version_id', 'HfFolderEntry': 'entry_id'}[model.__name__]
            return NS(**{key: 20}, **fields)
        with patch.object(AssetDao, 'entry', AsyncMock(return_value=entry)), \
             patch.object(AssetDao, 'asset', AsyncMock(return_value=source)), \
             patch.object(AssetDao, 'version', AsyncMock(return_value=version)), \
             patch.object(AssetDao, 'file', AsyncMock(return_value=NS(file_id=10, state='1'))), \
             patch.object(AssetDao, 'add', side_effect=insert), \
             patch.object(WorkspaceService, 'authorize', AsyncMock()) as authorize, \
             patch.object(WriteService, 'audit', return_value={}):
            result = await FolderContentService.copy(None, user, 3, 1, 2, 5, entry_id=7)
        self.assertEqual(entry.folder_id, 2)
        self.assertEqual(source.current_version_id, 9)
        self.assertEqual(created[1][1]['source_asset_version_id'], 9)
        self.assertEqual(created[1][1]['file_id'], 10)
        self.assertEqual(created[2][1]['folder_id'], 5)
        self.assertEqual(result.entry_id, 20)
        self.assertEqual([c.args[3] for c in authorize.await_args_list], ['asset:create', 'asset:read', 'asset:reference'])

    async def test_denied_copy_never_creates_records(self):
        with patch.object(AssetDao, 'entry', AsyncMock(return_value=NS(asset_id=8))), \
             patch.object(WorkspaceService, 'authorize', AsyncMock(side_effect=RuntimeError('无权限'))), \
             patch.object(AssetDao, 'add', AsyncMock()) as add:
            with self.assertRaises(RuntimeError):
                await FolderContentService.copy(None, NS(user=NS(user_id=4)), 3, 1, 2, 5, entry_id=7)
            add.assert_not_awaited()

"""目录素材数量聚合与权限边界。"""
import unittest
from unittest.mock import AsyncMock, Mock, patch
from exceptions.exception import PermissionException
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.service.folder_service import FolderService

class FolderCountTests(unittest.IsolatedAsyncioTestCase):
    async def test_counts_include_root_and_group_direct_children(self):
        db = Mock(execute=AsyncMock(return_value=Mock(all=Mock(return_value=[(None, 2), (8, 3), (9, 1)]))))
        self.assertEqual(await FolderDao.asset_counts(db, 4), {'total': 6, 'folders': {'8': 3, '9': 1}})
        sql = str(db.execute.call_args.args[0])
        self.assertIn('del_flag', sql)
        self.assertIn('GROUP BY', sql)

    async def test_denied_before_count_query(self):
        with patch('module_higgsfield.service.folder_service.WorkspaceService.authorize', AsyncMock(side_effect=PermissionException(message='无权限'))), patch.object(FolderDao, 'asset_counts', AsyncMock()) as query:
            with self.assertRaises(PermissionException):
                await FolderService.asset_counts(None, None, 2)
            query.assert_not_awaited()

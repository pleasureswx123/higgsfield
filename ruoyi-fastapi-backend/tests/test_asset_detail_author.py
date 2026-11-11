"""素材详情作者使用真实创建者，且受素材读取授权保护。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from module_higgsfield.service.asset_service import AssetService, AssetDao, WorkspaceDao, WorkspaceService


class AssetDetailAuthorTests(unittest.IsolatedAsyncioTestCase):
    async def test_author_projection_and_fallback(self):
        asset = SimpleNamespace(create_user_id=31, performer_id=32, del_flag='0')
        user = SimpleNamespace(user=SimpleNamespace(user_id=32), permissions={'asset:edit', 'asset:remove'})
        for author, name in [
            ({'nick_name': '制作人', 'user_name': 'maker', 'del_flag': '0'}, '制作人'),
            ({'nick_name': '', 'user_name': 'maker', 'del_flag': '0'}, 'maker'),
            ({'nick_name': '旧姓名', 'user_name': 'old', 'del_flag': '2'}, '已删除用户'),
            (None, '已删除用户'),
        ]:
            with self.subTest(name=name), \
                 patch.object(AssetDao, 'project_id', AsyncMock(return_value=2)), \
                 patch.object(AssetDao, 'asset', AsyncMock(return_value=asset)), \
                 patch.object(WorkspaceService, 'authorize', AsyncMock(return_value=(SimpleNamespace(status='0'), 'producer', set()))), \
                 patch.object(WorkspaceDao, 'permission_scopes', AsyncMock(return_value={'asset:edit': 'own', 'asset:remove': 'own'})), \
                 patch.object(AssetService, 'result', AsyncMock(return_value={'id': '23'})), \
                 patch.object(WorkspaceDao, 'user', AsyncMock(return_value=author)) as lookup:
                result = await AssetService.get(None, user, 23)
                lookup.assert_awaited_once_with(None, 31)
                self.assertEqual(result['author'], {'displayName': name})
                self.assertEqual(result.get('allowedActions'), ['asset:edit'])

    async def test_denied_asset_does_not_read_author(self):
        with patch.object(AssetDao, 'project_id', AsyncMock(return_value=2)), \
             patch.object(AssetDao, 'asset', AsyncMock(return_value=SimpleNamespace(create_user_id=31))), \
             patch.object(WorkspaceService, 'authorize', AsyncMock(side_effect=RuntimeError('无权访问'))), \
             patch.object(WorkspaceDao, 'user', AsyncMock()) as lookup:
            with self.assertRaises(RuntimeError):
                await AssetService.get(None, object(), 23)
            lookup.assert_not_awaited()

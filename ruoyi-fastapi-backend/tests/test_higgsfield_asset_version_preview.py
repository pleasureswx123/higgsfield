"""元素固定素材版本预览的授权与版本选择测试。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.dao.asset_dao import AssetDao


class AssetVersionPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_version_keeps_asset_authorization_and_fixed_version(self):
        db, user = object(), object()
        version = SimpleNamespace(version_id=13, asset_id=42)
        asset = SimpleNamespace(asset_id=42, current_version_id=99)
        with patch.object(AssetDao, 'version', AsyncMock(return_value=version)), \
             patch.object(AssetDao, 'asset', AsyncMock(return_value=asset)), \
             patch.object(AssetService, 'get', AsyncMock()) as authorize, \
             patch.object(AssetService, 'result', AsyncMock(return_value={'currentVersionId': '13'})) as serialize:
            result = await AssetService.get_version(db, user, 13)
            authorize.assert_awaited_once_with(db, user, 42)
            serialize.assert_awaited_once_with(db, asset, version)
            self.assertEqual(result['currentVersionId'], '13')

    async def test_denied_asset_cannot_preview_version(self):
        with patch.object(AssetDao, 'version', AsyncMock(return_value=SimpleNamespace(asset_id=42))), \
             patch.object(AssetService, 'get', AsyncMock(side_effect=RuntimeError('无权访问'))), \
             patch.object(AssetService, 'result', AsyncMock()) as serialize:
            with self.assertRaises(RuntimeError):
                await AssetService.get_version(object(), object(), 13)
            serialize.assert_not_awaited()

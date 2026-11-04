"""素材预览仅展示授权的业务生成信息。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from exceptions.exception import PermissionException
from module_higgsfield.service.asset_service import AssetService


class AssetGenerationInfoTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_version_has_no_generation_info(self):
        version = SimpleNamespace(version_id=1, source_output_id=None, source_asset_version_id=None)
        self.assertIsNone(await AssetService.generation_info(None, None, version))

    async def test_generation_projection_and_permission(self):
        version = SimpleNamespace(version_id=1, source_output_id=2)
        job = SimpleNamespace(project_id=2, actor_id=103, model_version_id=4, create_time='2026-11-03', input_snapshot={
            'prompt': {'content': [{'content': [{'type': 'text', 'text': '雨夜街头'}]}]},
            'parameters': {'resolution': '2K', 'quality': 'low', 'aspect_ratio': '16:9'},
            'internalSecret': 'must-not-leak',
        })
        with patch('module_higgsfield.dao.generated_output_dao.GeneratedOutputDao.get', AsyncMock(return_value=SimpleNamespace(job_id=4))), \
             patch('module_higgsfield.dao.generation_read_dao.GenerationReadDao.job', AsyncMock(return_value=job)), \
             patch('module_higgsfield.dao.generation_read_dao.GenerationReadDao.model', AsyncMock(return_value=SimpleNamespace(display_name='mm-imagen2'))), \
             patch('module_higgsfield.service.asset_service.WorkspaceService.authorize', AsyncMock()) as authorize:
            result = await AssetService.generation_info(None, None, version)
            self.assertEqual(result['prompt'], '雨夜街头')
            self.assertEqual(result['resolution'], '2K')
            self.assertNotIn('must-not-leak', str(result))
            authorize.side_effect = PermissionException(message='无权查看')
            self.assertIsNone(await AssetService.generation_info(None, None, version))

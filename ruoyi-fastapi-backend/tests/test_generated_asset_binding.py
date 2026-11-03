"""验证生成媒体归入提交目录及重放保护，不调用供应商。"""
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as Row
from unittest.mock import AsyncMock, patch

from module_higgsfield.service.generated_asset_binding_service import GeneratedAssetBindingService


class GeneratedAssetBindingTests(unittest.IsolatedAsyncioTestCase):
    async def bind(self, kind='video', folder=None, metadata=None):
        job = Row(job_id=7, project_id=2, actor_id=9,
                  input_snapshot={'billingMode': 'actual_usage', 'folderId': '5'})
        output = Row(kind=kind, output_id=8, ordinal=0, actual_metadata=metadata or {})
        file = Row(file_id=10, mime_type=f'{kind}/' + ('mp4' if kind == 'video' else 'png'),
                   width=1280, height=720, seconds=Decimal('5') if kind == 'video' else None)
        target = folder or Row(space_id=4, del_flag='0', folder_kind='media')
        with patch('module_higgsfield.service.generated_asset_binding_service.FolderDao.space', AsyncMock(return_value=Row(space_id=4))), \
             patch('module_higgsfield.service.generated_asset_binding_service.FolderDao.get', AsyncMock(return_value=target)), \
             patch('module_higgsfield.service.generated_asset_binding_service.AssetDao.add', AsyncMock(side_effect=[Row(asset_id=11), Row(version_id=12), Row()])) as add:
            await GeneratedAssetBindingService.bind(None, job, output, file, datetime.now(timezone.utc), 'worker')
            return output, add

    async def test_video_keeps_destination_author_file_and_duration(self):
        output, add = await self.bind()
        asset, version, entry = [call.kwargs for call in add.await_args_list]
        self.assertEqual(asset['media_type'], 'video')
        self.assertEqual(asset['create_user_id'], 9)
        self.assertEqual(asset['asset_name'], '生成视频-7-1.mp4')
        self.assertEqual(version['file_id'], 10)
        self.assertEqual(version['source_output_id'], 8)
        self.assertEqual(version['media_metadata']['seconds'], '5')
        self.assertEqual(entry['folder_id'], 5)
        self.assertEqual(output.actual_metadata['assetId'], '11')

    async def test_image_still_binds(self):
        _, add = await self.bind('image')
        self.assertEqual(add.await_args_list[0].kwargs['media_type'], 'image')

    async def test_replay_does_not_duplicate_asset(self):
        _, add = await self.bind(metadata={'assetId': '11'})
        add.assert_not_awaited()

    async def test_deleted_or_foreign_folder_does_not_redirect(self):
        for folder in (Row(space_id=4, del_flag='2', folder_kind='media'),
                       Row(space_id=99, del_flag='0', folder_kind='media')):
            output, add = await self.bind(folder=folder)
            add.assert_not_awaited()
            self.assertIn('destinationIssue', output.actual_metadata)

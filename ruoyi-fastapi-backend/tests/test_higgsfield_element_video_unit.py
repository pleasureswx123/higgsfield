"""元素图片与视频引用校验。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.element_content_service import ElementContentService

class ElementVideoTests(unittest.IsolatedAsyncioTestCase):
    async def validate_media(self, kind, mime, state='1', space=2):
        content = NS(property_values=[], media=[NS(asset_version_id='3')])
        source = (NS(), NS(media_type=kind, space_id=space, del_flag='0', create_user_id=1), NS(mime_type=mime, state=state))
        with patch('module_higgsfield.service.element_content_service.ElementDao.media_sources', AsyncMock(return_value=[source])), patch('module_higgsfield.service.element_content_service.WorkspaceService.authorize', AsyncMock()):
            return await ElementContentService.validate(None, NS(), 1, 2, content)

    async def test_image_and_video_are_supported(self):
        for kind,mime in [('image','image/png'),('video','video/mp4'),('video','video/webm')]:
            self.assertEqual(await self.validate_media(kind,mime), [])

    async def test_invalid_or_unavailable_reference_is_rejected(self):
        for args in [('document','application/pdf'),('video','image/png'),('video','video/mp4','0'),('video','video/mp4','1',99)]:
            with self.subTest(args=args), self.assertRaises(ServiceWarning):
                await self.validate_media(*args)

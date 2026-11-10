"""元素媒体同类型校验，不连接数据库。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.element_content_service import ElementContentService


class ElementMediaTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_one_media_type_per_element(self):
        for kinds in [('image', 'image'), ('video', 'video'), ('image', 'video'), ()]:
            with self.subTest(kinds=kinds):
                sources = [(NS(), NS(media_type=kind, space_id=1, del_flag='0', create_user_id=1),
                            NS(state='1', mime_type=kind + '/test')) for kind in kinds]
                content = NS(property_values=[], media=[NS(asset_version_id=str(i + 1)) for i in range(len(kinds))])
                with patch('module_higgsfield.service.element_content_service.ElementDao.media_sources', AsyncMock(return_value=sources)), patch('module_higgsfield.service.element_content_service.WorkspaceService.authorize', AsyncMock()):
                    if len(set(kinds)) > 1:
                        with self.assertRaises(ServiceWarning):
                            await ElementContentService.validate(None, NS(), 1, 1, content)
                    else:
                        self.assertEqual(await ElementContentService.validate(None, NS(), 1, 1, content), [])

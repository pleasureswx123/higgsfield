"""历史修订入口遵守元素权限并拒绝混用其他元素的修订。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.service.element_content_service import ElementContentService
from module_higgsfield.service.element_service import ElementService


class RevisionDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_requested_snapshot_after_authorization(self):
        revision = NS(element_id=7, revision_id=19)
        with patch.object(ElementService, 'authorized', AsyncMock()) as authorize, \
             patch.object(ElementDao, 'revision', AsyncMock(return_value=revision)), \
             patch.object(ElementContentService, 'result', AsyncMock(return_value={'id': '19'})):
            self.assertEqual(await ElementService.revision_detail('db', 'user', 7, 19), {'id': '19'})
            authorize.assert_awaited_once_with('db', 'user', 7, 'element:read')

    async def test_other_element_revision_is_not_exposed(self):
        with patch.object(ElementService, 'authorized', AsyncMock()), \
             patch.object(ElementDao, 'revision', AsyncMock(return_value=NS(element_id=8))), \
             patch.object(ElementContentService, 'result', AsyncMock()) as result:
            with self.assertRaises(ServiceWarning):
                await ElementService.revision_detail('db', 'user', 7, 19)
            result.assert_not_awaited()

    async def test_denied_reader_never_reads_revision(self):
        with patch.object(ElementService, 'authorized', AsyncMock(side_effect=PermissionException(message='无权访问'))), \
             patch.object(ElementDao, 'revision', AsyncMock()) as read:
            with self.assertRaises(PermissionException):
                await ElementService.revision_detail('db', 'user', 7, 19)
            read.assert_not_awaited()

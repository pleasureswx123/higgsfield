"""属性名称冲突检查，不连接数据库或修改用户数据。"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.element_vo import PropertyDefinitionCreate
from module_higgsfield.service.element_service import ElementService


class PropertyNameTests(unittest.IsolatedAsyncioTestCase):
    async def test_builtin_and_duplicate_names_are_rejected_before_write(self):
        prefix = 'module_higgsfield.service.element_service.'
        for name in ['描述', ' 描 述 ', '元素 ＩＤ', '备注', 'ＮＯＴＥ']:
            with self.subTest(name=name), ExitStack() as stack:
                for target, value in [
                    ('WriteService.lock', None), ('WriteService.replay', None),
                    ('WorkspaceService.authorize', None), ('FolderDao.space', NS(space_id=1)),
                    ('ElementDao.latest_definition', None),
                    ('ElementDao.definitions', ([NS(property_key='note', property_name='备注'), NS(property_key='english', property_name='note')], 2)),
                ]:
                    stack.enter_context(patch(prefix + target, AsyncMock(return_value=value)))
                add = stack.enter_context(patch(prefix + 'ElementDao.add', AsyncMock()))
                db = NS(rollback=AsyncMock())
                with self.assertRaises(ServiceWarning):
                    await ElementService.write_definition(db, NS(), PropertyDefinitionCreate(
                        propertyKey='new_property', name=name, valueType='text', options=[]
                    ), 'request-key', project_id=1)
                add.assert_not_awaited()
                db.rollback.assert_awaited_once()

"""任务卡片只发布已授权项目名称和平台费用摘要。"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.generation_read_service import GenerationReadService


class GenerationListContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_visible_summary_whitelists_platform_fields(self):
        job = SimpleNamespace(project_id=9, actor_id=2)
        allowed = {'generation:read', 'project:usage:read'}
        billing = {'billingVisibility': 'visible', 'billing': {
            'platform': {'amount': '1234567890123456.1234567890', 'currency': 'CNY', 'state': 'calculated', 'secret': 'hidden'},
            'usage': {'subjects': ['private']}, 'procurement': 'private',
        }}
        with patch('module_higgsfield.service.generation_read_service.WorkspaceService.authorize', AsyncMock(return_value=(SimpleNamespace(project_name='项目甲'), None, allowed))) as authorize, patch('module_higgsfield.service.generation_read_service.TaskBillingReadService.read', AsyncMock(return_value=billing)) as read:
            result = await GenerationReadService.list_context('db', 'user', job)
        authorize.assert_awaited_once_with('db', 'user', 9, 'generation:read', owner_id=2)
        read.assert_awaited_once_with('db', job, allowed)
        self.assertEqual(result, {'projectName': '项目甲', 'billingVisibility': 'visible', 'billingSummary': {
            'amount': '1234567890123456.1234567890', 'currency': 'CNY', 'state': 'calculated',
        }})

    async def test_hidden_and_unavailable_do_not_include_amount(self):
        for visibility in ('hidden', 'unavailable'):
            with self.subTest(visibility=visibility), patch('module_higgsfield.service.generation_read_service.WorkspaceService.authorize', AsyncMock(return_value=(SimpleNamespace(project_name='项目甲'), None, {'generation:read'}))), patch('module_higgsfield.service.generation_read_service.TaskBillingReadService.read', AsyncMock(return_value={'billingVisibility': visibility, 'billing': {'platform': {'amount': '99'}}})):
                result = await GenerationReadService.list_context(None, None, SimpleNamespace(project_id=9, actor_id=2))
                self.assertEqual(result, {'projectName': '项目甲', 'billingVisibility': visibility})

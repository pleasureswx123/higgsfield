"""成员展示补充登录账号，保持系统账号隔离。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from exceptions.exception import PermissionException
from module_higgsfield.service.project_workspace_service import WorkspaceService

class MemberIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_includes_account_without_changing_role(self):
        member = SimpleNamespace(user_id=104, role_id=3, status='0', revision=2, joined_time=None)
        with patch('module_higgsfield.service.project_workspace_service.WorkspaceDao.user', new=AsyncMock(return_value={'nick_name': '制作成员甲', 'user_name': 'hf_test_maker_a'})):
            result = await WorkspaceService.member_result(None, member)
        self.assertEqual(result['displayName'], '制作成员甲')
        self.assertEqual(result['userName'], 'hf_test_maker_a')
        self.assertEqual(result['roleId'], '3')

    async def test_system_admin_remains_hidden(self):
        with self.assertRaises(PermissionException):
            await WorkspaceService.member_result(None, SimpleNamespace(user_id=1))

    async def test_deleted_user_has_no_fabricated_account(self):
        member = SimpleNamespace(user_id=104, role_id=3, status='1', revision=2, joined_time=None)
        with patch('module_higgsfield.service.project_workspace_service.WorkspaceDao.user', new=AsyncMock(return_value=None)):
            result = await WorkspaceService.member_result(None, member)
        self.assertIsNone(result['userName'])
        self.assertEqual(result['displayName'], '已删除用户')

"""内置管理员身份不向用户查询、角色查询和在线列表暴露。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from exceptions.exception import ServiceException
from module_admin.controller.user_controller import query_detail_system_user
from module_admin.entity.vo.user_vo import UserRoleQueryModel
from module_admin.entity.vo.online_vo import OnlineQueryModel
from module_admin.service.user_service import UserService
from module_admin.service.online_service import OnlineService


class BuiltinAdminVisibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_detail_rejects_builtin_admin_before_database_read(self):
        for admin in (False, True):
            with self.assertRaises(ServiceException):
                await query_detail_system_user(None, None, SimpleNamespace(user=SimpleNamespace(admin=admin)), None, 1)

    async def test_role_detail_rejects_builtin_admin_before_database_read(self):
        with self.assertRaises(ServiceException):
            await UserService.get_user_role_allocated_list_services(None, UserRoleQueryModel(userId=1))

    async def test_online_list_hides_builtin_admin(self):
        redis = SimpleNamespace(keys=AsyncMock(return_value=['token']), get=AsyncMock(return_value='value'))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=redis)))
        with patch('module_admin.service.online_service.JwtUtil.decode', return_value={'user_id': 1, 'user_name': 'admin'}):
            self.assertEqual(await OnlineService.get_online_list_services(request, OnlineQueryModel()), [])

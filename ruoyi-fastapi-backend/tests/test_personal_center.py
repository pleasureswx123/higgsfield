"""个人中心资料边界和当前密码校验回归。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from module_admin.entity.vo.user_vo import ResetPasswordModel, UpdateUserProfileModel, ResetUserModel
from module_admin.service.user_service import UserService
from module_admin.dao.user_dao import UserDao
from exceptions.exception import ServiceException

class PersonalCenterTest(unittest.IsolatedAsyncioTestCase):
    def test_current_password_required(self):
        for payload in ({'newPassword': 'New123!'}, {'oldPassword': None, 'newPassword': 'New123!'}, {'oldPassword': '', 'newPassword': 'New123!'}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                ResetPasswordModel(**payload)

    def test_profile_rejects_privilege_fields(self):
        for field in ('userId', 'userName', 'roleIds', 'status'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                UpdateUserProfileModel(**{'nickName': '测试昵称', field: '1'})

    async def test_wrong_current_password_does_not_write(self):
        db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        with patch.object(UserDao, 'get_user_detail_by_id', AsyncMock(return_value={'user_basic_info': SimpleNamespace(password='hashed')})), patch.object(UserDao, 'edit_user_dao', AsyncMock()) as write, patch('module_admin.service.user_service.PwdUtil.verify_password', return_value=False):
            with self.assertRaises(ServiceException):
                await UserService.reset_user_services(db, ResetUserModel(userId=103, oldPassword='Wrong123!', password='New123!'))
            write.assert_not_awaited()
            db.commit.assert_not_awaited()

    async def test_successful_password_change_uses_hash_and_security_event(self):
        db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        with patch.object(UserDao, 'get_user_detail_by_id', AsyncMock(return_value={'user_basic_info': SimpleNamespace(password='old-hash')})), patch.object(UserDao, 'edit_user_dao', AsyncMock()) as write, patch('module_admin.service.user_service.PwdUtil.verify_password', side_effect=[True, False]), patch('module_admin.service.user_service.PwdUtil.get_password_hash', return_value='new-hash'), patch('module_admin.service.user_service.IdentitySecurityEventService.handle_user_event', AsyncMock()) as event:
            await UserService.reset_user_services(db, ResetUserModel(userId=103, oldPassword='Old123!', password='New123!', updateBy='test'))
            payload = write.await_args.args[1]
            self.assertEqual(payload['password'], 'new-hash')
            self.assertNotIn('old_password', payload)
            event.assert_awaited_once_with(db, 103, 'password_changed', actor='test')
            db.commit.assert_awaited_once()

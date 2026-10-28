"""测试历史按凭据版本过滤后分页，不透传秘密或越权历史。"""
import os
import unittest
from exceptions.exception import PermissionException, ServiceWarning
from tests import test_higgsfield_credential_test_requests as requests
from module_higgsfield.service.credential_test_service import CredentialTestService
from module_higgsfield.entity.vo.credential_test_vo import CredentialTestPage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestHistoryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = requests.CredentialTestRequestTests.asyncSetUp
    cleanup_schema = requests.CredentialTestRequestTests.cleanup_schema
    payload = requests.CredentialTestRequestTests.payload
    save = requests.CredentialTestRequestTests.save
    request = requests.CredentialTestRequestTests.request

    async def test_version_scope_pagination_and_permission(self):
        first, _ = await self.request()
        second, _ = await self.request()
        original = self.key_id
        other, _ = await self.save(self.payload(name='其他凭据', apiKey=self.secret + '-other'))
        self.key_id = int(other['data']['versionsSummary'][0]['id'])
        await self.request()
        async with self.sessions() as db:
            page = await CredentialTestService.listing(db, self.owner, original, CredentialTestPage(pageSize=1))
            self.assertEqual(page.total, 2)
            self.assertTrue(page.has_next)
            self.assertEqual(page.rows[0]['id'], second['data']['id'])
            page = await CredentialTestService.listing(db, self.owner, original, CredentialTestPage(pageSize=1, pageNum=2))
            self.assertFalse(page.has_next)
            self.assertEqual(page.rows[0]['id'], first['data']['id'])
            self.assertNotIn(self.secret, str(page.rows))
            with self.assertRaises(ServiceWarning):
                await CredentialTestService.listing(db, self.owner, 999999, CredentialTestPage())
        self.owner.permissions = []
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await CredentialTestService.listing(db, self.owner, original, CredentialTestPage())

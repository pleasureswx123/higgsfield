"""测试模型候选按连接区域和状态过滤，不借用模型管理权限。"""
import os
import unittest
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from tests import test_higgsfield_credential_test_executor as executors
from module_higgsfield.entity.do.model_do import HfModelProfileVersion
from module_higgsfield.entity.vo.credential_test_vo import CredentialTestPage
from module_higgsfield.service.credential_test_model_service import CredentialTestModelService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestModelTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = executors.CredentialTestExecutorTests.asyncSetUp
    cleanup_schema = executors.CredentialTestExecutorTests.cleanup_schema
    payload = executors.CredentialTestExecutorTests.payload
    save = executors.CredentialTestExecutorTests.save
    request = executors.CredentialTestExecutorTests.request

    async def test_matching_candidates_and_live_permission(self):
        async with self.sessions() as db:
            model_id = await db.scalar(text('SELECT model_id FROM hf_model_profile LIMIT 1'))
            for number, region, state in ((2, 'other', '0'), (3, 'eva', '3')):
                db.add(HfModelProfileVersion(model_id=model_id, version_no=number, region=region, status=state,
                    gateway_alias='excluded', capabilities={}))
            await db.commit()
        self.owner.permissions = ['credential:test']
        async with self.sessions() as db:
            result = await CredentialTestModelService.listing(db, self.owner, self.key_id, CredentialTestPage(pageSize=1))
            self.assertEqual(result.total, 1)
            self.assertEqual(result.rows[0]['id'], str(self.model_version_id))
            self.assertNotIn(self.secret, str(result))
            await db.execute(text("UPDATE hf_credential_version SET state='4',revoked_time=clock_timestamp()"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await CredentialTestModelService.listing(db, self.owner, self.key_id, CredentialTestPage())
        self.owner.permissions = []
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await CredentialTestModelService.listing(db, self.owner, self.key_id, CredentialTestPage())

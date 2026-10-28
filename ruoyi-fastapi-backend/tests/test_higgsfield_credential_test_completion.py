"""测试与调用事实同事务回收，不丢失潜在消费或覆盖已结束结果。"""
import os
import unittest
from sqlalchemy import text
from tests import test_higgsfield_credential_test_requests as requests
from module_higgsfield.service.credential_test_intent_service import CredentialTestIntentService
from module_higgsfield.service.credential_test_completion_service import CredentialTestCompletionService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CredentialTestCompletionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = requests.CredentialTestRequestTests.asyncSetUp
    cleanup_schema = requests.CredentialTestRequestTests.cleanup_schema
    payload = requests.CredentialTestRequestTests.payload
    save = requests.CredentialTestRequestTests.save
    request = requests.CredentialTestRequestTests.request

    async def begin(self):
        receipt, _ = await self.request()
        identity = int(receipt['data']['id'])
        async with self.sessions() as db:
            intent = await CredentialTestIntentService.begin(db, identity, lambda binding: {'model': 'fixture'})
        return identity, intent.call_id

    async def test_unknown_is_atomic_terminal_and_never_not_sent(self):
        identity, call_id = await self.begin()
        result = dict(transport='timeout', authentication='unknown', acceptance='unknown', issue='TRANSPORT_UNKNOWN')
        async with self.sessions() as db:
            self.assertFalse(await CredentialTestCompletionService.not_sent(db, identity, 'CONFIG_CHANGED'))
            self.assertTrue(await CredentialTestCompletionService.finish(db, identity, call_id, result))
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT * FROM hf_credential_test'))).mappings().one()
            call = (await db.execute(text('SELECT * FROM hf_provider_call'))).mappings().one()
            self.assertEqual(row['state'], '2')
            self.assertEqual(call['state'], '3')
            self.assertEqual(call['acceptance'], 'unknown')
            self.assertEqual(row['finished_time'], call['finished_time'])
            self.assertEqual(row['result'], call['response_metadata'])
            await db.rollback()
            self.assertFalse(await CredentialTestCompletionService.finish(db, identity, call_id,
                dict(transport='response', httpStatus=401, authentication='failed', acceptance='rejected', issue='AUTH_REJECTED')))
            self.assertIsNone(await CredentialTestIntentService.begin(db, identity, lambda binding: {'model': 'fixture'}))

    async def test_wrong_identity_rolls_back_and_auth_rejection_completes(self):
        identity, call_id = await self.begin()
        result = dict(transport='response', httpStatus=401, authentication='failed', acceptance='rejected', issue='AUTH_REJECTED')
        async with self.sessions() as db:
            with self.assertRaises(ValueError):
                await CredentialTestCompletionService.finish(db, identity, call_id + 1, result)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            await db.rollback()
            self.assertTrue(await CredentialTestCompletionService.finish(db, identity, call_id, result))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '2')
            self.assertEqual(await db.scalar(text('SELECT http_status FROM hf_provider_call')), 401)

    async def test_not_sent_does_not_create_call_and_cannot_be_claimed(self):
        receipt, _ = await self.request()
        identity = int(receipt['data']['id'])
        async with self.sessions() as db:
            self.assertTrue(await CredentialTestCompletionService.not_sent(db, identity, 'PROBE_UNSUPPORTED'))
            self.assertIsNone(await CredentialTestIntentService.begin(db, identity, lambda binding: {'model': 'fixture'}))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
            result = await db.scalar(text('SELECT result FROM hf_credential_test'))
            self.assertEqual(result['transport'], 'not_sent')

    async def test_success_without_bound_model_is_rejected(self):
        identity, call_id = await self.begin()
        async with self.sessions() as db:
            with self.assertRaises(ValueError):
                await CredentialTestCompletionService.finish(db, identity, call_id,
                    dict(transport='response', httpStatus=200, authentication='passed', acceptance='accepted',
                         issue='NONE', modelVerified=True, outputCount=1))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_credential_test')), '0')

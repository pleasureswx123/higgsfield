"""调用查询使用真实数据库验证范围，并验证元数据白名单。"""
import importlib.util
import os
import unittest
from pathlib import Path
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import ServiceWarning, PermissionException
from tests import test_higgsfield_admin_scope as scope_tests
from tests import test_higgsfield_job_storage as job_tests
from tests import test_higgsfield_provider_call_storage as call_tests
from module_higgsfield.entity.vo.provider_call_query_vo import ProviderCallQuery
from module_higgsfield.service.provider_call_read_service import ProviderCallReadService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderCallReadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = scope_tests.AdminScopeTests.cleanup_schema
    create = scope_tests.AdminScopeTests.create
    scope = scope_tests.AdminScopeTests.scope
    job = job_tests.JobStorageTests.job
    call = call_tests.ProviderCallStorageTests.call

    async def asyncSetUp(self):
        await scope_tests.AdminScopeTests.asyncSetUp(self)
        self.actor.permissions = ['operations:read']
        async with self.engine.begin() as conn:
            await conn.execute(text("UPDATE sys_menu SET perms='operations:read' WHERE menu_id=9001"))
            for name in ('20261027_29_jobs_outbox.py', '20261027_35_provider_calls.py', '20261028_52_operations_read.py'):
                spec = importlib.util.spec_from_file_location('call_read_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
        async with self.sessions() as db:
            job = self.job(project_id=self.project_id)
            db.add(job)
            await db.flush()
            self.job_id = job.job_id
            call = self.call(job_id=job.job_id, request_metadata={'connectionVersionId': '9007199254740993', 'Authorization': 'secret', 'prompt': '正文'}, response_metadata={'outputCount': 2, 'url': 'https://secret.invalid'})
            db.add_all([call, self.call(job_id=None, cost_center_id=7, account_id=2)])
            await db.flush()
            self.call_id = call.call_id
            await db.commit()

    async def listing(self, **values):
        async with self.sessions() as db:
            return await ProviderCallReadService.listing(db, self.actor, ProviderCallQuery(**values))

    async def detail(self, identity):
        async with self.sessions() as db:
            return await ProviderCallReadService.detail(db, self.actor, identity)

    async def test_scope_detail_projection_and_revocation(self):
        self.assertEqual((await self.listing()).total, 0)
        with self.assertRaises(ServiceWarning):
            await self.detail(self.call_id)
        await self.scope('4')
        self.assertEqual((await self.listing()).total, 1)
        detail = await self.detail(self.call_id)
        self.assertEqual(detail['state'], 'planned')
        self.assertEqual(detail['requestMetadata'], {'connectionVersionId': '9007199254740993'})
        self.assertEqual(detail['responseMetadata'], {'outputCount': 2})
        self.assertNotIn('credential_version_id', detail)
        self.assertIsNone(detail['startedAt'])
        await self.scope('1')
        page = await self.listing(pageSize=1)
        self.assertEqual(page.total, 2)
        self.assertTrue(page.has_next)
        self.assertEqual((await self.listing(accountId='2')).rows[0]['costCenterId'], '7')
        self.assertEqual((await self.listing(jobId=str(self.job_id), state='planned')).total, 1)
        self.assertEqual((await self.listing(state='unknown')).total, 0)
        self.assertEqual((await self.listing(**{'to': '2000-01-01T00:00:00Z'})).total, 0)
        with self.assertRaises(ServiceWarning):
            await self.detail(9223372036854775807)
        async with self.sessions() as db:
            await db.execute(text('DELETE FROM sys_role_menu WHERE menu_id=9001'))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.detail(self.call_id)


class ProviderCallProjectionTests(unittest.TestCase):
    def test_nested_secrets_and_wrong_types_are_not_projected(self):
        self.assertEqual(ProviderCallReadService.metadata({
            'Authorization': 'Bearer secret', 'response': {'prompt': '正文'},
            'connectionVersionId': 'https://private', 'outputCount': True,
            'businessCode': 'https://secret.invalid', 'mode': 'synchronous',
            'byteSize': 10, 'usage': {'raw': 'base64'},
        }), {'mode': 'synchronous', 'byteSize': 10})

    def test_query_requires_valid_ids_states_and_aware_time(self):
        from pydantic import ValidationError
        for payload in ({'jobId': 1}, {'accountId': '0'}, {'state': '2'},
                        {'from': '2026-10-01T00:00:00'},
                        {'from': '2026-10-02T00:00:00Z', 'to': '2026-10-01T00:00:00Z'}):
            with self.assertRaises(ValidationError):
                ProviderCallQuery(**payload)

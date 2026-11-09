"""真实数据库汇总的日期分组、历史部门和范围过滤。"""

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from module_higgsfield.entity.vo.usage_query_vo import UsageQuery
from module_higgsfield.entity.vo.usage_query_vo import StudioUsageQuery
from exceptions.exception import PermissionException
from uuid import uuid4
from module_higgsfield.service.usage_summary_service import UsageSummaryService
from tests import test_higgsfield_billing_admin as admin


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class UsageSummaryTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = admin.BillingAdminTests.cleanup_schema
    migrate = admin.BillingAdminTests.migrate
    job = admin.BillingAdminTests.job
    seed = admin.BillingAdminTests.seed
    create = admin.BillingAdminTests.create

    async def test_cost_center_summary_adjustments_boundaries_and_access(self):
        spec = importlib.util.spec_from_file_location(
            'summary_centers', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_56_cost_centers.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        base = {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00',
                'purpose': 'platform', 'scope': 'cost_center', 'groupBy': 'cost_center'}
        query = UsageQuery.model_validate(base)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_cost_center SET cost_center_id=9007199254740993,active='N'"))
            await db.execute(text('UPDATE hf_billing_subject SET job_id=NULL,cost_center_id=9007199254740993'))
            await db.commit()
        await admin.BillingAdminTests.save(self, str(uuid4()))
        async with self.sessions() as db:
            result = await UsageSummaryService.summary(db, self.owner, query)
            self.assertEqual(result['scope'], 'cost_center')
            row = result['rows'][0]
            self.assertEqual(row['groupKey'], '9007199254740993')
            self.assertEqual(row['displayName'], '管理员测试')
            self.assertEqual(row['totalKnownAmount'], '0.0100000000')
            self.assertEqual(row['inputTokens'], '3')
            for changes in ({'costCenterId': '2'}, {'currency': 'CNY'}, {'purpose': 'procurement'},
                            {'from': '2026-10-31T00:00:00+08:00', 'to': base['from']}):
                self.assertEqual((await UsageSummaryService.summary(db, self.owner,
                    UsageQuery.model_validate(base | changes)))['rows'], [])
            project_query = UsageQuery.model_validate(base | {'scope': 'project', 'groupBy': 'project'})
            self.assertEqual((await UsageSummaryService.summary(db, self.owner, project_query))['rows'], [])
            day = await UsageSummaryService.summary(db, self.owner,
                UsageQuery.model_validate(base | {'groupBy': 'day', 'businessTimezone': 'UTC'}))
            self.assertEqual(day['rows'][0]['groupKey'], '2026-10-31')
            with patch('module_higgsfield.service.usage_summary_service.AdminScopeService.context',
                AsyncMock(return_value=({'user_id': 2, 'dept_id': None}, [{'role_id': 1, 'data_scope': '5'}]))):
                with self.assertRaises(PermissionException):
                    await UsageSummaryService.summary(db, self.owner, query)
            with self.assertRaises(PermissionException):
                await UsageSummaryService.personal_summary(db, self.owner, query)
            with self.assertRaises(PermissionException):
                await UsageSummaryService.project_summary(db, self.owner, 1, query)
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await UsageSummaryService.summary(db, self.owner, query)



    async def test_studio_summary_remains_unavailable_with_project_permissions(self):
        query = StudioUsageQuery.model_validate(
            {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00', 'groupBy': 'project'}
        )
        async with self.sessions() as db:
            # 即使拥有项目用量权限，制作端也不得读取已迁移到管理端的费用汇总。
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'project:usage:read','project' FROM hf_project_role WHERE code='owner' ON CONFLICT (role_id,permission_code) DO UPDATE SET data_scope=EXCLUDED.data_scope"))
            with self.assertRaises(PermissionException):
                await UsageSummaryService.personal_summary(db, self.owner, query)
            with self.assertRaises(PermissionException):
                await UsageSummaryService.project_summary(db, self.owner, 1, query)

    async def asyncSetUp(self):
        await admin.BillingAdminTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'summary_models', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_13_models.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_billing_event SET create_time='2026-10-31T16:00:00Z'"))
            await db.execute(
                text('UPDATE hf_creation_job SET department_snapshot=CAST(:snapshot AS jsonb)'),
                {'snapshot': '{"deptId":7,"deptName":"历史部门"}'},
            )
            await db.commit()

    async def test_groups_use_business_timezone_snapshot_and_scoped_facts(self):
        base = {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00', 'purpose': 'platform'}
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET kind='image'"))
            images = await UsageSummaryService.summary(db, self.owner, UsageQuery.model_validate(base | {'groupBy': 'project', 'generationType': 'image'}))
            videos = await UsageSummaryService.summary(db, self.owner, UsageQuery.model_validate(base | {'groupBy': 'project', 'generationType': 'video'}))
            self.assertEqual(images['rows'][0]['totalKnownAmount'], '0.0200000000')
            self.assertEqual(videos['rows'], [])
            for group, expected in (
                ('project', '1'),
                ('user', 'system'),
                ('department', '7'),
                ('model', 'unknown'),
                ('day', '2026-11-01'),
                ('week', '2026-10-26'),
                ('month', '2026-11'),
            ):
                query = UsageQuery.model_validate(base | {'groupBy': group})
                result = await UsageSummaryService.summary(db, self.owner, query)
                self.assertEqual(result['rows'][0]['groupKey'], expected)
                self.assertEqual(result['rows'][0]['totalKnownAmount'], '0.0200000000')
                self.assertEqual(result['rows'][0]['inputTokens'], '3')
                if group == 'department':
                    self.assertEqual(result['rows'][0]['displayName'], '历史部门')
            query = UsageQuery.model_validate(base | {'groupBy': 'day', 'businessTimezone': 'UTC'})
            result = await UsageSummaryService.summary(db, self.owner, query)
            self.assertEqual(result['rows'][0]['groupKey'], '2026-10-31')
            with patch(
                'module_higgsfield.service.usage_summary_service.AdminScopeService.context',
                AsyncMock(return_value=({'user_id': 2, 'dept_id': None}, [{'role_id': 1, 'data_scope': '5'}])),
            ):
                self.assertEqual((await UsageSummaryService.summary(db, self.owner, query))['rows'], [])

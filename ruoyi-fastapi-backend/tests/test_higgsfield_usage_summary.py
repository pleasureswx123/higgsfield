"""真实数据库汇总的日期分组、历史部门和范围过滤。"""

import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from module_higgsfield.entity.vo.usage_query_vo import UsageQuery
from module_higgsfield.entity.vo.usage_query_vo import StudioUsageQuery
from module_higgsfield.entity.do.billing_do import HfBillingEvent
from module_higgsfield.entity.do.usage_do import HfBillingSubject
from exceptions.exception import PermissionException
from decimal import Decimal
from datetime import datetime, UTC
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



    async def test_personal_summary_excludes_other_actors_and_removed_projects(self):
        await self.create(name='项目二')
        query = StudioUsageQuery.model_validate(
            {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00', 'groupBy': 'project'}
        )
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'project:usage:read','project' FROM hf_project_role WHERE code='owner'"
                )
            )
            for actor_id, amount in ((1, '3'), (2, '99')):
                job = self.job(project_id=2, actor_id=actor_id, idempotency_key=f'cross-project:{actor_id}')
                db.add(job)
                await db.flush()
                subject = HfBillingSubject(
                    account_id=1,
                    job_id=job.job_id,
                    origin_call_id=100 + actor_id,
                    subject_kind='generation',
                    identity_key=f'cross:{actor_id}',
                    **self.audit,
                )
                db.add(subject)
                await db.flush()
                db.add(
                    HfBillingEvent(
                        subject_id=subject.subject_id,
                        purpose='platform',
                        price_version_id=1,
                        currency='USD',
                        amount=Decimal(amount),
                        state='1',
                        **(self.audit | {'create_time': datetime(2026, 10, 31, 16, tzinfo=UTC)}),
                    )
                )
            await db.commit()
            result = await UsageSummaryService.personal_summary(db, self.owner, query)
            self.assertEqual([row['totalKnownAmount'] for row in result['rows']], ['0.0200000000', '3.0000000000'])
            await db.execute(text("UPDATE hf_project_member SET status='1' WHERE project_id=2 AND user_id=1"))
            await db.commit()
            result = await UsageSummaryService.personal_summary(db, self.owner, query)
            self.assertEqual(len(result['rows']), 1)
            self.assertEqual(result['rows'][0]['groupKey'], '1')
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='project:usage:read'"))
            await db.commit()
            with self.assertRaises(PermissionException):
                await UsageSummaryService.personal_summary(db, self.owner, query)

    async def test_studio_project_permission_scope_and_revocation(self):
        query = StudioUsageQuery.model_validate(
            {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00', 'groupBy': 'project'}
        )
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await UsageSummaryService.project_summary(db, self.owner, 1, query)
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'project:usage:read','project' FROM hf_project_role WHERE code='owner'"
                )
            )
            other_job = self.job(actor_id=2, idempotency_key='other-user')
            db.add(other_job)
            await db.flush()
            subject = HfBillingSubject(
                account_id=1,
                job_id=other_job.job_id,
                origin_call_id=99,
                subject_kind='generation',
                identity_key='other:99',
                **self.audit,
            )
            db.add(subject)
            await db.flush()
            db.add(
                HfBillingEvent(
                    subject_id=subject.subject_id,
                    purpose='platform',
                    price_version_id=1,
                    currency='USD',
                    amount=Decimal('99'),
                    state='1',
                    **(self.audit | {'create_time': datetime(2026, 10, 31, 16, tzinfo=UTC)}),
                )
            )
            await db.commit()
            result = await UsageSummaryService.project_summary(db, self.owner, 1, query)
            self.assertEqual(result['rows'][0]['totalKnownAmount'], '99.0200000000')
            await db.execute(
                text(
                    "UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='project:usage:read'"
                )
            )
            await db.commit()
            result = await UsageSummaryService.project_summary(db, self.owner, 1, query)
            self.assertEqual(result['rows'][0]['totalKnownAmount'], '0.0200000000')
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='project:usage:read'"))
            await db.commit()
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
            for group, expected in (
                ('project', '1'),
                ('user', '1'),
                ('department', '7'),
                ('model', 'unknown'),
                ('day', '2026-11-01'),
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

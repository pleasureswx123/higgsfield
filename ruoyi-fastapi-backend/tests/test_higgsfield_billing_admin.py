"""管理费用调整的真实权限、幂等与审计回滚。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from exceptions.exception import PermissionException
from module_higgsfield.service.billing_admin_service import BillingAdminService
from module_higgsfield.service.billing_worker_service import BillingWorker
from module_higgsfield.entity.vo.billing_adjustment_vo import BillingAdjustmentInput
from module_higgsfield.entity.vo.billing_query_vo import BillingQuery
from module_higgsfield.entity.do.billing_do import HfBillingEvent
from decimal import Decimal
from tests import test_higgsfield_billing_worker as worker
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class BillingAdminTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.BillingWorkerTests.cleanup_schema
    migrate = worker.BillingWorkerTests.migrate
    job = worker.BillingWorkerTests.job
    seed = worker.BillingWorkerTests.seed
    create = projects.ProjectDatabaseTests.create

    async def test_list_time_window_is_timezone_aware_and_right_exclusive(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_billing_event SET create_time='2026-10-31T16:00:00Z'"))
            await db.commit()
            before = BillingQuery.model_validate(
                {'from': '2026-10-01T00:00:00+08:00', 'to': '2026-11-01T00:00:00+08:00'}
            )
            after = BillingQuery.model_validate(
                {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00', 'userId': '1'}
            )
            self.assertEqual((await BillingAdminService.listing(db, self.owner, before)).total, 0)
            self.assertEqual((await BillingAdminService.listing(db, self.owner, after)).total, 1)
            self.assertEqual(
                (await BillingAdminService.listing(db, self.owner, after.model_copy(update={'user_id': '2'}))).total, 0
            )

    async def test_cost_center_listing_and_detail_keep_project_scope_separate(self):
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_billing_subject SET job_id=NULL,cost_center_id=9007199254740993'))
            await db.commit()
            self.assertEqual((await BillingAdminService.listing(db, self.owner, BillingQuery())).total, 0)
            result = await BillingAdminService.listing(db, self.owner,
                BillingQuery(scope='cost_center', costCenterId='9007199254740993'))
            self.assertEqual(result.total, 1)
            self.assertIsNone(result.rows[0]['jobId'])
            self.assertEqual(result.rows[0]['costCenterId'], '9007199254740993')
            detail = await BillingAdminService.detail(db, self.owner, self.event_id)
            self.assertIsNone(detail['jobId'])
            self.assertEqual(detail['costCenterId'], '9007199254740993')
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await BillingAdminService.detail(db, self.owner, self.event_id)

    async def test_cost_center_adjustment_replay_audit_and_no_project_side_effects(self):
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_billing_subject SET job_id=NULL,cost_center_id=123'))
            await db.commit()
            before_jobs = (await db.execute(text('SELECT job_id,revision,event_sequence FROM hf_creation_job ORDER BY job_id'))).all()
            before_ledger = await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry'))
            before_events = await db.scalar(text('SELECT count(*) FROM hf_task_event'))
        key = str(uuid4())
        first, _ = await self.save(key)
        replay, repeated = await self.save(key)
        self.assertTrue(repeated)
        self.assertEqual(first, replay)
        async with self.sessions() as db:
            detail = await BillingAdminService.detail(db, self.owner, self.event_id)
            self.assertEqual(detail['effectiveAmount'], '0.0100000000')
            self.assertEqual(detail['amount'], '0.0200000000')
            self.assertEqual(before_jobs, (await db.execute(text('SELECT job_id,revision,event_sequence FROM hf_creation_job ORDER BY job_id'))).all())
            self.assertEqual(before_ledger, await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')))
            self.assertEqual(before_events, await db.scalar(text('SELECT count(*) FROM hf_task_event')))
            audit = await db.scalar(text("SELECT before_after FROM hf_audit_log WHERE object_type='billing_event'"))
            self.assertEqual(audit['costCenterId'], '123')
        self.payload = self.payload.model_copy(update={'revision': '2', 'delta_amount': '-0.005'})
        with patch('module_higgsfield.service.billing_admin_service.PriceSourceDao.audit', side_effect=RuntimeError('模拟审计失败')):
            with self.assertRaises(RuntimeError):
                await self.save(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 1)
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.save(key)

    async def test_list_filters_purpose_scope_and_adjusted_amount_before_pagination(self):
        await self.save(str(uuid4()))
        async with self.sessions() as db:
            subject_id = await db.scalar(text('SELECT subject_id FROM hf_billing_subject'))
            db.add(
                HfBillingEvent(
                    subject_id=subject_id,
                    purpose='procurement',
                    price_version_id=999,
                    currency='USD',
                    amount=Decimal('99'),
                    state='1',
                    **self.audit,
                )
            )
            await db.commit()
            page = await BillingAdminService.listing(db, self.owner, BillingQuery(pageSize=1))
            self.assertEqual(page.total, 1)
            self.assertEqual(page.rows[0]['effectiveAmount'], '0.0100000000')
            self.assertEqual(page.rows[0]['purpose'], 'platform')
            self.assertEqual((await BillingAdminService.listing(db, self.owner, BillingQuery(currency='CNY'))).total, 0)
            self.assertEqual(
                (await BillingAdminService.listing(db, self.owner, BillingQuery(pageNum=2, pageSize=1))).rows, []
            )
            with patch(
                'module_higgsfield.service.billing_admin_service.AdminScopeService.context',
                AsyncMock(return_value=({'user_id': 2, 'dept_id': None}, [{'role_id': 1, 'data_scope': '5'}])),
            ):
                restricted = await BillingAdminService.listing(db, self.owner, BillingQuery(pageSize=1))
                self.assertEqual(restricted.total, 0)
                self.assertEqual(restricted.rows, [])
                with self.assertRaises(PermissionException):
                    await BillingAdminService.listing(db, self.owner, BillingQuery(purpose='procurement'))

    async def test_detail_preserves_original_and_reports_adjusted_balance(self):
        await self.save(str(uuid4()))
        async with self.sessions() as db:
            result = await BillingAdminService.detail(db, self.owner, self.event_id)
            self.assertEqual(result['amount'], '0.0200000000')
            self.assertEqual(result['effectiveAmount'], '0.0100000000')
            self.assertEqual(result['revision'], '2')
            self.assertEqual(result['lines'][0]['itemCode'], 'input')
            self.assertEqual(result['usage']['inputTokens'], '3')
            self.assertEqual(result['adjustments'][0]['reason'], '核实部分退款')
            for secret in ('raw_usage', 'request_metadata', 'credential', 'accountId'):
                self.assertNotIn(secret, str(result))
            self.owner.permissions = ['billing:adjust']
            with self.assertRaises(PermissionException):
                await BillingAdminService.detail(db, self.owner, self.event_id)

    async def asyncSetUp(self):
        await worker.BillingWorkerTests.asyncSetUp(self)
        for name in ('20261027_16_audit.py', '20261028_41_billing_adjust_permission.py'):
            spec = importlib.util.spec_from_file_location(
                'billing_admin_setup', Path(__file__).resolve().parents[1] / 'alembic/versions' / name
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.owner.user.admin = True
        async with self.sessions() as db:
            await db.execute(text('ALTER TABLE sys_user ADD COLUMN dept_id bigint'))
            await db.commit()
        await self.create()
        await BillingWorker(self.sessions, 'seed').process(self.identity)
        async with self.sessions() as db:
            self.event_id = await db.scalar(text('SELECT event_id FROM hf_billing_event'))
        self.payload = BillingAdjustmentInput(revision='1', deltaAmount='-0.01', reason='核实部分退款')

    async def save(self, key):
        async with self.sessions() as db:
            return await BillingAdminService.adjust(db, self.owner, self.event_id, self.payload, key)

    async def test_replay_and_live_permission_recheck(self):
        key = str(uuid4())
        first, repeated = await self.save(key)
        self.assertFalse(repeated)
        second, repeated = await self.save(key)
        self.assertTrue(repeated)
        self.assertEqual(first, second)
        # 新请求键重复同一费用版本也只返回原调整，不重复入账。
        third, _ = await self.save(str(uuid4()))
        self.assertEqual(first['data'], third['data'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 1)
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='billing_event'")), 1
            )
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.save(key)

    async def test_audit_failure_rolls_back_adjustment_and_task_event(self):
        async with self.sessions() as db:
            before = await db.scalar(text('SELECT revision FROM hf_creation_job'))
        with patch(
            'module_higgsfield.service.billing_admin_service.PriceSourceDao.audit', side_effect=RuntimeError('test')
        ):
            with self.assertRaises(RuntimeError):
                await self.save(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_adjustment')), 0)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), before)

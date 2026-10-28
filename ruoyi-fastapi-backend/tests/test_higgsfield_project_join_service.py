"""审批事务使用真实数据库，申请入口暂由测试固定记录代替。"""
import importlib.util
import asyncio
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.do.project_join_do import HfProjectJoinRequest
from module_higgsfield.entity.vo.project_join_vo import JoinReview, JoinQuery
from module_higgsfield.service.project_join_service import ProjectJoinService
from module_higgsfield.service.write_service import WriteService
from tests.test_higgsfield_project_join_storage import JoinStorageTests
from tests.test_higgsfield_projects import ProjectDatabaseTests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class JoinServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = JoinStorageTests.cleanup_schema
    migrate = JoinStorageTests.migrate
    create = ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await JoinStorageTests.asyncSetUp(self)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_16_audit.py'
        spec = importlib.util.spec_from_file_location('join_audit', path)
        self.migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        result, _ = await self.create()
        self.project_id = int(result['data']['id'])
        async with self.sessions() as db:
            self.role_id = str(await db.scalar(text("SELECT role_id FROM hf_project_role WHERE code='viewer'")))
            row = HfProjectJoinRequest(project_id=self.project_id, user_id=2, reason='参与制作', **WriteService.audit(self.other))
            db.add(row); await db.flush(); self.identity = row.request_id; await db.commit()

    async def review(self, decision='approved', revision='1', key='review'):
        async with self.sessions() as db:
            return await ProjectJoinService.review(db, self.owner, self.identity,
                JoinReview(revision=revision, decision=decision, roleId=self.role_id if decision == 'approved' else None, reason='审批说明'), 'join-review-test-' + key)

    async def test_approve_atomic_replay_and_revoke(self):
        result, replay = await self.review()
        self.assertFalse(replay); self.assertEqual(result['data']['status'], 'approved')
        self.assertTrue((await self.review())[1])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_project_member WHERE user_id=2 AND status='0'")), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
            page = await ProjectJoinService.listing(db, self.owner, self.project_id, JoinQuery(status='approved'))
            self.assertEqual(page.total, 1)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='member:manage'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.review()

    async def test_reject_processed_state_and_audit_rollback(self):
        with patch('module_higgsfield.service.project_join_service.PriceSourceDao.audit', new=AsyncMock(side_effect=RuntimeError('审计失败'))):
            with self.assertRaises(RuntimeError):
                await self.review()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_project_join_request')), '0')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_member WHERE user_id=2')), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_api_idempotency_record WHERE result_type='project_join_request'")), 0)
        await self.review('rejected')
        with self.assertRaises(ServiceWarning):
            await self.review(revision='2', key='another')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_member WHERE user_id=2')), 0)
            self.assertEqual(await db.scalar(text('SELECT reason FROM hf_project_join_request')), '参与制作')
            self.assertEqual(await db.scalar(text('SELECT reason FROM hf_audit_log')), '审批说明')

    async def test_disabled_applicant_and_readonly_project(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE sys_user SET status='1' WHERE user_id=2")); await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.review()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project SET status='1'")); await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.review('rejected')

    async def test_concurrent_decisions_have_one_winner(self):
        results = await asyncio.gather(self.review(key='approve'), self.review('rejected', key='reject'), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, tuple) for item in results), 1)
        self.assertEqual(sum(isinstance(item, ServiceWarning) for item in results), 1)
        async with self.sessions() as db:
            state = await db.scalar(text('SELECT status FROM hf_project_join_request'))
            count = await db.scalar(text('SELECT count(*) FROM hf_project_member WHERE user_id=2'))
            self.assertEqual(count, 1 if state == '1' else 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_audit_log')), 1)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_project_join_request')), 2)

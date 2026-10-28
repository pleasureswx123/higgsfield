"""作品协作状态的真实事务、幂等、并发修订与权限边界。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.output_status_vo import OutputStatusUpdate
from module_higgsfield.service.output_status_service import OutputStatusService
from module_higgsfield.service.output_read_service import OutputReadService
from tests import test_higgsfield_output_read as reads


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class OutputStatusTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create
    ready = reads.OutputReadTests.ready

    async def asyncSetUp(self):
        await reads.OutputReadTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('review_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_08_review_events.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'content:review','project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"))
            await db.commit()

    async def change(self, key=None, revision='1', status='review'):
        async with self.sessions() as db:
            return await OutputStatusService.update(db, self.owner, self.identity,
                OutputStatusUpdate(revision=revision, workStatus=status, reason='提交审核'), key or str(uuid4()))

    async def test_state_history_replay_and_technical_states_are_independent(self):
        await self.ready()
        async with self.sessions() as db:
            before = (await db.execute(text('SELECT orchestration_state,upstream_state,billing_state FROM hf_creation_job'))).one()
            self.assertIn('output:work-status', (await OutputReadService.get(db, self.owner, self.identity))['allowedActions'])
        key = str(uuid4())
        result, replayed = await self.change(key)
        self.assertFalse(replayed)
        self.assertEqual(result['data']['workStatus'], 'review')
        self.assertEqual(result['data']['revision'], '2')
        self.assertTrue((await self.change(key))[1])
        with self.assertRaises(ServiceWarning):
            await self.change(revision='1', status='approved')
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT orchestration_state,upstream_state,billing_state FROM hf_creation_job'))).one(), before)
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_review_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)

    async def test_not_ready_revocation_and_readonly_are_rejected(self):
        with self.assertRaises(ServiceWarning):
            await self.change()
        await self.ready()
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='content:review'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.change()
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'content:review','project' FROM hf_project_role WHERE code='owner'"))
            await db.execute(text("UPDATE hf_project SET status='1'"))
            await db.commit()
            self.assertNotIn('output:work-status', (await OutputReadService.get(db, self.owner, self.identity))['allowedActions'])
        with self.assertRaises(ServiceWarning):
            await self.change()

    async def test_event_failure_rolls_back_status_history_and_idempotency(self):
        await self.ready()
        with patch('module_higgsfield.service.output_status_service.JobEventDao.output', AsyncMock(side_effect=RuntimeError('测试事件写入失败'))):
            with self.assertRaises(RuntimeError):
                await self.change()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT work_status FROM hf_generated_output')), '0')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_review_event')), 0)

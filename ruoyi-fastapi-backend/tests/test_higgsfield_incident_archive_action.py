"""管理归档恢复沿用真实事务，校验范围、幂等与审计原因。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import PermissionException, ServiceWarning
from tests import test_higgsfield_incident_read as incidents
from module_higgsfield.entity.vo.incident_action_vo import IncidentAction
from module_higgsfield.service.generation_archive_retry_service import GenerationArchiveRetryService
from module_higgsfield.service.incident_read_service import IncidentReadService
from module_higgsfield.dao.price_source_dao import PriceSourceDao


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class IncidentArchiveActionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = incidents.IncidentReadTests.cleanup_schema
    create = incidents.IncidentReadTests.create
    scope = incidents.IncidentReadTests.scope
    job = incidents.IncidentReadTests.job
    call = incidents.IncidentReadTests.call

    async def asyncSetUp(self):
        await incidents.IncidentReadTests.asyncSetUp(self)
        self.actor.user.user_name = '运维处理者'
        self.actor.permissions.append('operations:recover')
        async with self.engine.begin() as conn:
            for name in ('20261027_16_audit.py', '20261028_54_operations_recover.py'):
                spec = importlib.util.spec_from_file_location('incident_action_migration', Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        module.upgrade()
                await conn.run_sync(migrate)
            await conn.execute(text("INSERT INTO sys_role_menu(role_id,menu_id) SELECT 2,menu_id FROM sys_menu WHERE perms='operations:recover'"))
            await conn.execute(text("""INSERT INTO hf_generated_output(job_id,ordinal,kind,archive_state,source_url_ciphertext,source_expires_time,create_time,update_time)
                VALUES (:id,0,'image','3',decode('abcd','hex'),clock_timestamp()+interval '1 hour',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""), {'id': self.job_id})

    async def retry(self, key=None):
        async with self.sessions() as db:
            return await GenerationArchiveRetryService.retry_managed(db, self.actor, self.job_id,
                IncidentAction(revision='1', action='retry_archive', reason='已修复归档网络', evidenceRef='ticket:123'), key or str(uuid4()))

    async def test_scope_replay_and_audit_without_new_call(self):
        with self.assertRaises(ServiceWarning):
            await self.retry()
        await self.scope('4')
        async with self.sessions() as db:
            detail = await IncidentReadService.detail(db, self.actor, self.job_id)
            self.assertEqual(detail['allowedActions'], ['retry_archive', 'requery', 'close_tracking'])
        key = str(uuid4())
        first, replayed = await self.retry(key)
        self.assertFalse(replayed)
        again, replayed = await self.retry(key)
        self.assertTrue(replayed)
        self.assertEqual(first, again)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '0')
            self.assertEqual(await db.scalar(text('SELECT reason FROM hf_audit_log')), '已修复归档网络')
            self.assertEqual(await db.scalar(text("SELECT before_after->>'evidenceRef' FROM hf_audit_log")), 'ticket:123')
            self.assertEqual((await IncidentReadService.detail(db, self.actor, self.job_id))['allowedActions'], ['requery', 'close_tracking'])
            await db.execute(text("DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms='operations:recover')"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.retry(key)

    async def test_expiry_and_audit_failure_preserve_state(self):
        await self.scope('1')
        with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计故障'))):
            with self.assertRaises(RuntimeError):
                await self.retry()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job')), 1)
            self.assertEqual(await db.scalar(text('SELECT archive_state FROM hf_generated_output')), '3')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)
            await db.execute(text("UPDATE hf_generated_output SET source_expires_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
            self.assertEqual((await IncidentReadService.detail(db, self.actor, self.job_id))['allowedActions'], ['requery', 'close_tracking'])
        with self.assertRaises(ServiceWarning):
            await self.retry()

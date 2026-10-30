"""验证所有权转让、唯一性、重放和失败回滚。"""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from tests import test_higgsfield_projects as fixtures
from module_higgsfield.service.project_ownership_service import ProjectOwnershipService
from module_higgsfield.service.project_permission_service import ProjectPermissionService
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.entity.vo.project_workspace_vo import OwnershipTransfer

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要独立数据库schema')
class OwnershipTests(fixtures.ProjectDatabaseTests):
    async def test_transfer_replay_and_rollback(self):
        pid, roles = await self.workspace_fixture()
        await self.mutate(pid, 'add', {'userId': '2', 'roleId': roles['producer']})
        async with self.sessions() as db:
            revision = str(await db.scalar(text('SELECT revision FROM hf_project WHERE project_id=:pid'), {'pid': pid}))
            await db.rollback()
            payload = OwnershipTransfer(userId='2', revision=revision, targetRevision='1')
            key = str(uuid4())
            with patch.object(PriceSourceDao, 'audit', AsyncMock(side_effect=RuntimeError('审计失败'))):
                with self.assertRaises(RuntimeError):
                    await ProjectOwnershipService.transfer(db, self.owner, pid, payload, key)
            self.assertEqual(await db.scalar(text('SELECT owner_user_id FROM hf_project WHERE project_id=:pid'), {'pid': pid}), 1)
            await db.rollback()
            with patch.object(PriceSourceDao, 'audit', AsyncMock()) as audit:
                result, replay = await ProjectOwnershipService.transfer(db, self.owner, pid, payload, key)
                self.assertFalse(replay)
                repeated, replay = await ProjectOwnershipService.transfer(db, self.owner, pid, payload, key)
                self.assertTrue(replay)
                self.assertEqual(repeated, result)
                audit.assert_awaited_once()
            rows = (await db.execute(text("SELECT m.user_id,r.code FROM hf_project_member m JOIN hf_project_role r USING(role_id) WHERE project_id=:pid ORDER BY user_id"), {'pid': pid})).all()
            self.assertEqual(rows, [(1, 'admin'), (2, 'owner')])
            self.assertEqual(await db.scalar(text('SELECT create_user_id FROM hf_project WHERE project_id=:pid'), {'pid': pid}), 1)
            self.assertFalse((await ProjectPermissionService.read(db, self.owner, pid))['canEdit'])
            self.assertTrue((await ProjectPermissionService.read(db, self.other, pid))['canEdit'])
            await db.rollback()
            with self.assertRaises(PermissionException):
                await ProjectOwnershipService.transfer(db, self.owner, pid, payload, str(uuid4()))
    async def test_disabled_target_and_revision_conflict(self):
        pid, roles = await self.workspace_fixture()
        await self.mutate(pid, 'add', {'userId': '2', 'roleId': roles['viewer']})
        async with self.sessions() as db:
            revision = str(await db.scalar(text('SELECT revision FROM hf_project WHERE project_id=:pid'), {'pid': pid}))
            await db.rollback()
            with self.assertRaises(ServiceWarning):
                await ProjectOwnershipService.transfer(db, self.owner, pid, OwnershipTransfer(userId='2', revision=revision, targetRevision='999'), str(uuid4()))
            await db.execute(text("UPDATE sys_user SET status='1' WHERE user_id=2"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await ProjectOwnershipService.transfer(db, self.owner, pid, OwnershipTransfer(userId='2', revision=revision, targetRevision='1'), str(uuid4()))

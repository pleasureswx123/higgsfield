"""验证两层角色的默认权限、Owner例外及接收人资格。"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from tests import test_higgsfield_projects as fixtures
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.dao.usage_summary_dao import UsageSummaryDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.project_permission_service import ProjectPermissionService
from module_higgsfield.service.project_ownership_service import ProjectOwnershipService
from module_higgsfield.service.generation_access_service import GenerationAccessService
from module_higgsfield.dao.project_governance_dao import ProjectGovernanceDao
from module_higgsfield.entity.vo.project_workspace_vo import OwnershipTransfer, ProjectPermissionUpdate

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要独立schema')
class RoleBoundaryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ProjectDatabaseTests.asyncSetUp
    cleanup_schema = fixtures.ProjectDatabaseTests.cleanup_schema
    create = fixtures.ProjectDatabaseTests.create
    workspace_fixture = fixtures.ProjectDatabaseTests.workspace_fixture
    mutate = fixtures.ProjectDatabaseTests.mutate

    async def test_defaults_and_explicit_override(self):
        pid, roles = await self.workspace_fixture()
        await self.mutate(pid, 'add', {'userId': '2', 'roleId': roles['producer']})
        async with self.sessions() as db:
            scopes = await WorkspaceDao.permission_scopes(db, 'producer', pid)
            self.assertEqual(scopes['generation:create'], 'project')
            self.assertEqual(scopes['asset:edit'], 'own')
            viewer = await WorkspaceDao.permission_scopes(db, 'viewer', pid)
            self.assertEqual(viewer['asset:read'], 'project')
            self.assertNotIn('generation:create', viewer)
            self.assertNotIn('asset:download', viewer)
            await ProjectPermissionService.save(db, self.owner, pid, ProjectPermissionUpdate(revision='0', overrides={'producer': {'generation:create': 'none'}}), str(uuid4()))
            with self.assertRaises(PermissionException):
                await WorkspaceService.authorize(db, self.other, pid, 'generation:create')

    async def test_owner_worker_and_system_ceiling(self):
        pid, roles = await self.workspace_fixture()
        await self.mutate(pid, 'add', {'userId': '2', 'roleId': roles['producer']})
        restricted = SimpleNamespace(permissions=['project:read'], user=self.owner.user)
        async with self.sessions() as db:
            await WorkspaceService.authorize(db, restricted, pid, 'generation:create')
            await WorkspaceService.authorize(db, restricted, pid, 'project:archive')
            with patch.object(ProjectGovernanceDao, 'locked', AsyncMock(return_value=SimpleNamespace(del_flag='0',status='0'))):
                await GenerationAccessService.require(db, SimpleNamespace(project_id=pid, actor_id=1))
                with self.assertRaises(ServiceWarning):
                    await GenerationAccessService.require(db, SimpleNamespace(project_id=pid, actor_id=2))
            await db.rollback()
            with self.assertRaises(PermissionException):
                await WorkspaceService.authorize(db, SimpleNamespace(permissions=[],user=self.owner.user), pid, 'asset:read')

    async def test_transfer_requires_studio_access(self):
        pid, roles = await self.workspace_fixture()
        await self.mutate(pid, 'add', {'userId': '2', 'roleId': roles['viewer']})
        async with self.sessions() as db:
            revision = str(await db.scalar(text('SELECT revision FROM hf_project WHERE project_id=:pid'), {'pid': pid}))
            await db.execute(text('DELETE FROM sys_user_role WHERE user_id=2'))
            await db.commit()
            with self.assertRaises(ServiceWarning) as caught:
                await ProjectOwnershipService.transfer(db, self.owner, pid, OwnershipTransfer(userId='2',revision=revision,targetRevision='1'), str(uuid4()))
            self.assertEqual(caught.exception.data['errorCode'], 'STUDIO_ACCESS_REQUIRED')
            self.assertEqual(await db.scalar(text('SELECT owner_user_id FROM hf_project WHERE project_id=:pid'), {'pid': pid}), 1)

    async def test_usage_permission_cannot_be_reenabled(self):
        pid, roles = await self.workspace_fixture()
        async with self.sessions() as db:
            self.assertNotIn('project:usage:read', await WorkspaceDao.permission_scopes(db, 'owner', pid))
            with self.assertRaises(PermissionException):
                await ProjectPermissionService.save(db, self.owner, pid, ProjectPermissionUpdate(revision='0', overrides={'producer': {'project:usage:read': 'own'}}), str(uuid4()))

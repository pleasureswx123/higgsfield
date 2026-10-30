"""验证当前项目权限覆盖、并发和不可越权的边界。"""
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.dao.generation_actor_dao import GenerationActorDao
from module_higgsfield.entity.vo.project_workspace_vo import ProjectPermissionUpdate
from module_higgsfield.service.project_permission_service import ProjectPermissionService
from tests.test_higgsfield_projects import ProjectDatabaseTests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立schema测试')
class ProjectPermissionTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = ProjectDatabaseTests.asyncSetUp
    cleanup_schema = ProjectDatabaseTests.cleanup_schema
    create = ProjectDatabaseTests.create

    async def test_override_isolation_revision_replay_and_defaults(self):
        first, _ = await self.create()
        second, _ = await self.create()
        project_id = int(first['data']['id'])
        async with self.sessions() as db:
            initial = await ProjectPermissionService.read(db, self.owner, project_id)
            self.assertTrue(initial['canEdit'])
            defaults = await WorkspaceDao.permission_scopes(db, 'producer')
            payload = ProjectPermissionUpdate(revision='0', overrides={'producer': {'generation:create': 'project'}})
            key = str(uuid4())
            result, replayed = await ProjectPermissionService.save(db, self.owner, project_id, payload, key)
            self.assertFalse(replayed)
            self.assertEqual(result['data']['revision'], '1')
            repeated, replayed = await ProjectPermissionService.save(db, self.owner, project_id, payload, key)
            self.assertTrue(replayed)
            self.assertEqual(result, repeated)
            scopes = await WorkspaceDao.permission_scopes(db, 'producer', project_id)
            self.assertEqual(scopes['generation:create'], 'project')
            self.assertEqual(await WorkspaceDao.permission_scopes(db, 'producer', int(second['data']['id'])), defaults)
            with self.assertRaises(ServiceWarning):
                await ProjectPermissionService.save(db, self.owner, project_id, payload, str(uuid4()))
            await ProjectPermissionService.save(db, self.owner, project_id, ProjectPermissionUpdate(revision='1', overrides={'producer': {'generation:create': 'none'}}), str(uuid4()))
            self.assertNotIn('generation:create', await WorkspaceDao.permission_scopes(db, 'producer', project_id))

    async def test_owner_and_system_ceiling_cannot_be_overridden(self):
        with self.assertRaises(PermissionException):
            ProjectPermissionService.validate({'owner': {'member:manage': 'none'}}, ['*:*:*'])
        with self.assertRaises(PermissionException):
            ProjectPermissionService.validate({'producer': {'member:manage': 'project'}}, ['*:*:*'])
        with self.assertRaises(PermissionException):
            ProjectPermissionService.validate({'producer': {'generation:create': 'project'}}, ['project:read'])
        with self.assertRaises(PermissionException):
            ProjectPermissionService.validate({'viewer': {'generation:create': 'own'}}, ['*:*:*'])

    async def test_member_cannot_configure_and_worker_rechecks_revocation(self):
        result, _ = await self.create()
        pid = int(result['data']['id'])
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_member(project_id,user_id,role_id,status,joined_time,revision,create_by,update_by) SELECT :pid,2,role_id,'0',CURRENT_TIMESTAMP,1,'test','test' FROM hf_project_role WHERE code='producer'"), {'pid': pid})
            await db.commit()
            with self.assertRaises(PermissionException):
                await ProjectPermissionService.save(db, self.other, pid, ProjectPermissionUpdate(revision='0', overrides={}), str(uuid4()))
            await ProjectPermissionService.save(db, self.owner, pid, ProjectPermissionUpdate(revision='0', overrides={'producer': {'generation:create': 'project'}}), str(uuid4()))
            self.assertTrue(await GenerationActorDao.project_access(db, pid, 2))
            await db.rollback()
            await ProjectPermissionService.save(db, self.owner, pid, ProjectPermissionUpdate(revision='1', overrides={'producer': {'generation:create': 'none'}}), str(uuid4()))
            self.assertFalse(await GenerationActorDao.project_access(db, pid, 2))

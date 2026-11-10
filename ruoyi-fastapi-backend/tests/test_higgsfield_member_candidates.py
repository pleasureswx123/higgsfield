"""真实 PostgreSQL 隔离环境验证人员筛选与资格变更。"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.project_workspace_service import WorkspaceService
from sqlalchemy import text
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from tests import test_higgsfield_projects as project_fixture

@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class MemberCandidateTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = project_fixture.ProjectDatabaseTests.asyncSetUp
    cleanup_schema = project_fixture.ProjectDatabaseTests.cleanup_schema
    async def test_eligible_paging_and_roles(self):
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO sys_user VALUES (3,'1','0','disabled','停用'),(4,'0','2','deleted','删除'),(5,'0','0','no_role','无角色'),(6,'0','0','maker','制作人员')"))
            await db.execute(text("INSERT INTO sys_user_role VALUES (3,5),(4,5),(6,5),(6,5)"))
            rows,total = await WorkspaceDao.eligible_users(db, 999, size=1)
            self.assertEqual(total, 2)
            self.assertEqual(len(rows), 1)
            next_rows,_ = await WorkspaceDao.eligible_users(db, 999, page=2, size=1)
            self.assertNotEqual(rows[0]['user_id'], next_rows[0]['user_id'])
            rows,total = await WorkspaceDao.eligible_users(db, 999, keyword='制作')
            self.assertEqual([r['user_id'] for r in rows], [6])
            rows,_ = await WorkspaceDao.eligible_users(db, 999, keyword='MAKER')
            self.assertEqual(len(rows), 1)
            rows,_ = await WorkspaceDao.eligible_users(db, 999, keyword='%')
            self.assertEqual(len(rows), 0)
            await db.execute(text("UPDATE sys_role SET status='1' WHERE role_id=5"))
            rows,total = await WorkspaceDao.eligible_users(db, 999)
            self.assertEqual(total, 0)
            self.assertEqual(rows, [])

class MemberCandidatePermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reject_when_system_role_revoked_after_selection(self):
        with patch.object(WorkspaceDao, 'roles', AsyncMock(return_value=[SimpleNamespace(role_id=3, code='viewer')])), \
             patch.object(WorkspaceDao, 'user', AsyncMock(return_value={'status':'0','del_flag':'0'})), \
             patch.object(WorkspaceDao, 'eligible_users', AsyncMock(return_value=([],0))), \
             patch.object(WorkspaceDao, 'member', AsyncMock()) as member:
            with self.assertRaises(ServiceWarning):
                await WorkspaceService.grant_member(None, None, 2, 104, '3', 'owner')
            member.assert_not_called()

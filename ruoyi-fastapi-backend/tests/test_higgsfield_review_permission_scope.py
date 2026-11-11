"""审核授权必须是明确的项目范围，旧本人范围不能冒充审批权限。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from exceptions.exception import PermissionException
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.dao.project_permission_dao import ProjectPermissionDao
from module_higgsfield.service.project_permission_service import ProjectPermissionService


class ReviewPermissionScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_own_review_is_not_effective(self):
        rows = [('producer', 'content:review', 'own'), ('producer', 'asset:edit', 'own')]
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))
        scopes = await WorkspaceDao.permission_scopes(db, 'producer')
        self.assertNotIn('content:review', scopes)
        self.assertEqual(scopes['asset:edit'], 'own')

    async def test_explicit_project_review_is_preserved(self):
        db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))
        config = SimpleNamespace(overrides={'producer': {'content:review': 'project'}})
        with patch.object(ProjectPermissionDao, 'get', AsyncMock(return_value=config)):
            scopes = await WorkspaceDao.permission_scopes(db, 'producer', 8)
        self.assertEqual(scopes['content:review'], 'project')

    async def test_cannot_save_own_review_scope(self):
        with self.assertRaises(PermissionException):
            ProjectPermissionService.validate({'producer': {'content:review': 'own'}}, ['*:*:*'])
        ProjectPermissionService.validate({'producer': {'content:review': 'project'}}, ['*:*:*'])

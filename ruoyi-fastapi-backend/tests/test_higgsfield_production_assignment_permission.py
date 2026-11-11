"""制作责任仅影响编辑范围，不授予删除或审核权。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from exceptions.exception import PermissionException
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class AssignedProductionPermissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_assignee_can_edit_but_cannot_remove_creators_content(self):
        user = NS(user=NS(user_id=20), permissions={'project:read', 'asset:edit', 'asset:remove'})
        with patch.object(ProjectDao, 'get_project', AsyncMock(return_value=(NS(status='0'), 'producer'))), \
             patch.object(WorkspaceDao, 'permission_scopes', AsyncMock(return_value={
                 'asset:edit': 'own', 'asset:remove': 'own'})):
            _, _, allowed = await WorkspaceService.authorize(
                object(), user, 1, 'asset:edit', owner_id=10, responsibility_id=20)
            self.assertIn('asset:edit', allowed)
            self.assertNotIn('asset:remove', allowed)

    async def test_reassigned_creator_cannot_continue_editing_under_own_scope(self):
        user = NS(user=NS(user_id=10), permissions={'project:read', 'element:edit'})
        with patch.object(ProjectDao, 'get_project', AsyncMock(return_value=(NS(status='0'), 'producer'))), \
             patch.object(WorkspaceDao, 'permission_scopes', AsyncMock(return_value={'element:edit': 'own'})):
            with self.assertRaises(PermissionException):
                await WorkspaceService.authorize(
                    object(), user, 1, 'element:edit', owner_id=10, responsibility_id=20)

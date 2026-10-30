"""验证停用制作端财务入口及旧授权隔离。"""
import unittest
from types import SimpleNamespace
from exceptions.exception import PermissionException
from module_higgsfield.service.usage_summary_service import UsageSummaryService
from module_higgsfield.service.task_billing_read_service import TaskBillingReadService
from module_higgsfield.service.admin_scope_service import AdminScopeService

class FinanceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_summaries_denied(self):
        with self.assertRaises(PermissionException):
            await UsageSummaryService.personal_summary(None, None, None)
        with self.assertRaises(PermissionException):
            await UsageSummaryService.project_summary(None, None, 1, None)

    async def test_task_amount_hidden_even_with_old_permission(self):
        self.assertEqual(await TaskBillingReadService.read(None, None, {'project:usage:read'}), {'billingVisibility': 'hidden'})

    async def test_project_permissions_do_not_grant_finance(self):
        with self.assertRaises(PermissionException):
            await AdminScopeService.context(None, SimpleNamespace(permissions=['project:read', 'project:usage:read']), 'billing:read')

"""动作必须经过服务授权并写入固定版本证据。"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.review_dao import ReviewDao
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.vo.production_vo import ProductionAction
from module_higgsfield.service.production_review_service import ProductionReviewService as Service
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.asset_lifecycle_service import AssetLifecycleService
from module_higgsfield.entity.vo.asset_vo import AssetStatus
from tests import test_higgsfield_asset_status_unit as legacy_asset_tests


class ProductionReviewServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_element_form_cannot_approve_content(self):
        payload = NS(performer_id=None, work_status='approved')
        with patch.object(WorkspaceService, 'authorize', AsyncMock()), self.assertRaises(ServiceWarning):
            await ElementService.validate_fields(AsyncMock(), NS(user=NS(user_id=20)), 1, payload,
                                                 NS(work_status='1', create_user_id=20, performer_id=None))

    async def test_legacy_asset_status_endpoint_cannot_bypass_submission(self):
        asset = NS(create_user_id=20, performer_id=None, revision=1, del_flag='0', work_status='working')
        stack, _ = legacy_asset_tests.AssetStatusTests().context(asset)
        with stack, patch.object(WorkspaceDao, 'lock_project', AsyncMock()), self.assertRaises(ServiceWarning) as error:
            await AssetLifecycleService.mutate(AsyncMock(), NS(user=NS(user_id=20, user_name='制作乙')), 3, 'status',
                                               AssetStatus(revision='1', workStatus='approved'), 'key')
        self.assertIn('提交审核', error.exception.message)

    async def test_viewer_cannot_be_assigned_as_maker(self):
        with patch.object(WorkspaceDao, 'user', AsyncMock(return_value={'status': '0', 'del_flag': '0'})), \
             patch.object(ProjectDao, 'get_project', AsyncMock(return_value=(NS(status='0'), 'viewer'))), \
             patch.object(WorkspaceDao, 'permission_scopes', AsyncMock(return_value={'asset:read': 'project'})):
            with self.assertRaises(ServiceWarning):
                await Service.validate_performer(AsyncMock(), 1, 'asset', 20)

    def context(self, state='working', submitted=True):
        self.db = AsyncMock()
        self.user = NS(user=NS(user_id=20, user_name='制作乙'))
        self.asset = NS(asset_id=3, current_version_id=7, revision=4, work_status=state,
                        create_user_id=10, performer_id=20)
        stack = ExitStack()
        stack.enter_context(patch.object(Service, 'context', AsyncMock(return_value=(self.asset, NS(project_id=1, status='0')))))
        self.auth = stack.enter_context(patch.object(WorkspaceService, 'authorize', AsyncMock()))
        self.record = stack.enter_context(patch.object(ReviewDao, 'record', AsyncMock()))
        stack.enter_context(patch.object(ReviewDao, 'submitted', AsyncMock(return_value=submitted)))
        stack.enter_context(patch.object(Service, 'check_ready', AsyncMock()))
        stack.enter_context(patch.object(Service, 'get', AsyncMock(return_value={'workStatus': 'review'})))
        stack.enter_context(patch.object(WriteService, 'lock', AsyncMock()))
        stack.enter_context(patch.object(WriteService, 'replay', AsyncMock(return_value=None)))
        stack.enter_context(patch.object(WriteService, 'finish', AsyncMock(return_value=({}, False))))
        return stack

    async def test_assigned_maker_submits_with_edit_permission_and_version_evidence(self):
        with self.context():
            await Service.act(self.db, self.user, 'asset', 3,
                              ProductionAction(revision='4', versionId='7', action='submit'), 'key')
            self.assertEqual(self.asset.work_status, 'review')
            self.assertEqual(self.asset.revision, 5)
            self.assertEqual(self.auth.await_args.args[3], 'asset:edit')
            self.assertEqual(self.auth.await_args.kwargs['owner_id'], 20)
            self.assertEqual(self.record.await_args.kwargs['version_id'], 7)
            self.assertEqual(self.record.await_args.kwargs['action'], 'submit')

    async def test_approval_does_not_accept_own_scope(self):
        with self.context('review'):
            await Service.act(self.db, self.user, 'asset', 3,
                              ProductionAction(revision='4', versionId='7', action='approve'), 'key')
            self.assertEqual(self.auth.await_args.args[3], 'content:review')
            self.assertIsNone(self.auth.await_args.kwargs['owner_id'])
            self.assertEqual(self.asset.work_status, 'approved')

    async def test_legacy_review_cannot_be_approved_without_version_submission(self):
        with self.context('review', submitted=False):
            with self.assertRaises(ServiceWarning):
                await Service.act(self.db, self.user, 'asset', 3,
                                  ProductionAction(revision='4', versionId='7', action='approve'), 'key')
            self.record.assert_not_awaited()
            self.db.rollback.assert_awaited_once()

    async def test_stale_version_does_not_write_event(self):
        with self.context('review'):
            with self.assertRaises(ServiceWarning):
                await Service.act(self.db, self.user, 'asset', 3,
                                  ProductionAction(revision='4', versionId='6', action='approve'), 'key')
            self.assertEqual(self.asset.work_status, 'review')
            self.record.assert_not_awaited()

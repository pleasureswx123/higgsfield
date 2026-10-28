"""素材状态的权限、修订及持久化写入契约。"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from module_higgsfield.entity.vo.asset_vo import AssetStatus
from module_higgsfield.service.asset_lifecycle_service import AssetLifecycleService
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.folder_dao import FolderDao

class AssetStatusTests(unittest.IsolatedAsyncioTestCase):
    def context(self, asset, denied=False, replay=None):
        stack = ExitStack()
        for target, name, result in [(AssetDao,'project_id',1),(AssetDao,'asset',asset),
            (AssetDao,'asset_entry',NS(folder_id=2)),(FolderDao,'space',NS(space_id=1)),
            (WriteService,'lock',None),(WriteService,'replay',replay),(AssetDao,'flush',None),
            (WriteService,'finish',({'ok': True},False)),(AssetService,'result',{})]:
            stack.enter_context(patch.object(target,name,AsyncMock(return_value=result)))
        auth=stack.enter_context(patch.object(WorkspaceService,'authorize',AsyncMock(side_effect=RuntimeError('无审核权限') if denied else None)))
        return stack,auth

    async def test_all_statuses_saved_with_review_permission(self):
        for status in ['working','review','approved','rejected','none']:
            asset=NS(create_user_id=2,revision=1,del_flag='0',work_status='none')
            stack,auth=self.context(asset)
            with stack:
                await AssetLifecycleService.mutate(AsyncMock(),NS(user=NS(user_name='测试',user_id=2)),3,'status',AssetStatus(revision='1',workStatus=status),'key')
            self.assertEqual(asset.work_status,status)
            self.assertEqual(asset.revision,2)
            self.assertEqual(auth.await_args.args[3],'content:review')

    async def test_denial_and_revision_conflict_do_not_write(self):
        for denied,revision in [(True,'1'),(False,'2')]:
            asset=NS(create_user_id=2,revision=1,del_flag='0',work_status='none')
            stack,_=self.context(asset,denied)
            db=AsyncMock()
            with stack, self.assertRaises(Exception):
                await AssetLifecycleService.mutate(db,NS(user=NS(user_name='测试',user_id=2)),3,'status',AssetStatus(revision=revision,workStatus='approved'),'key')
            self.assertEqual(asset.work_status,'none')
            db.rollback.assert_awaited_once()

    async def test_replay_does_not_increment_revision(self):
        asset=NS(create_user_id=2,revision=2,del_flag='0',work_status='approved')
        stack,_=self.context(asset,replay={'saved': True})
        with stack:
            result=await AssetLifecycleService.mutate(AsyncMock(),NS(user=NS(user_name='测试',user_id=2)),3,'status',AssetStatus(revision='1',workStatus='approved'),'key')
        self.assertEqual(result,({'saved':True},True))
        self.assertEqual(asset.revision,2)

    def test_unknown_status_rejected(self):
        with self.assertRaises(ValidationError):
            AssetStatus(revision='1',workStatus='published')

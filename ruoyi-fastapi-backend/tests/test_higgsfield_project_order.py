"""项目排序的输入、权限、修订校验和幂等事务测试。"""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from module_higgsfield.entity.vo.project_preference_vo import ProjectOrderUpdate
from module_higgsfield.service.project_preference_service import PreferenceService


class ProjectOrderTests(unittest.IsolatedAsyncioTestCase):
    def test_duplicate_project_rejected(self):
        with self.assertRaises(ValidationError):
            ProjectOrderUpdate(items=[{'projectId': '1', 'revision': '0'}] * 2)

    async def run_order(self, conflict=False, forbidden=False, replay=None):
        db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
        user = SimpleNamespace(user=SimpleNamespace(user_id=9))
        payload = {'items': [{'projectId': '2', 'revision': '1'}, {'projectId': '1', 'revision': '1'}]}
        rows = {identity: SimpleNamespace(project_id=identity, preference_id=identity, revision=1,
            is_pinned='N', is_hidden='N', collection_id=None, order_num=99) for identity in [1, 2]}
        if conflict:
            rows[1].revision = 2
        base = 'module_higgsfield.service.project_preference_service.'
        with ExitStack() as stack:
            def mock(name, **kwargs):
                return stack.enter_context(patch(base + name, **kwargs))
            mock('WriteService.lock', new_callable=AsyncMock)
            lock = mock('WorkspaceDao.lock_project', new_callable=AsyncMock)
            mock('WorkspaceService.authorize', new_callable=AsyncMock, side_effect=ValueError('无权访问') if forbidden else None)
            mock('PreferenceDao.lock_user', new_callable=AsyncMock)
            mock('WriteService.replay', new_callable=AsyncMock, return_value=replay)
            mock('PreferenceDao.preference', new_callable=AsyncMock, side_effect=lambda _db, _uid, identity, _lock: rows[identity])
            mock('WorkspaceService.conflict', side_effect=ValueError('修订冲突'))
            mock('WriteService.audit', return_value={'update_by': '测试', 'update_time': None})
            finish = mock('WriteService.finish', new_callable=AsyncMock, return_value=({'code': 200}, False))
            if conflict or forbidden:
                with self.assertRaises(ValueError):
                    await PreferenceService.reorder(db, user, payload, 'test-key')
                db.rollback.assert_awaited_once()
                finish.assert_not_awaited()
                self.assertTrue(all(row.order_num == 99 for row in rows.values()))
            else:
                result = await PreferenceService.reorder(db, user, payload, 'test-key')
                self.assertEqual([call.args[1] for call in lock.await_args_list], [1, 2])
                if replay:
                    self.assertEqual(result, (replay, True))
                    finish.assert_not_awaited()
                    self.assertEqual(rows[1].revision, 1)
                else:
                    self.assertEqual((rows[2].order_num, rows[1].order_num), (0, 1))
                    self.assertEqual(rows[1].revision, 2)
                    finish.assert_awaited_once()

    async def test_atomic_order(self):
        await self.run_order()

    async def test_revision_conflict_before_any_change(self):
        await self.run_order(conflict=True)

    async def test_membership_required(self):
        await self.run_order(forbidden=True)

    async def test_idempotent_replay(self):
        await self.run_order(replay={'code': 200, 'data': []})

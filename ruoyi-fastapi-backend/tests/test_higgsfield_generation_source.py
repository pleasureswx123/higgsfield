"""来源追溯只发布同项目、当前授权可读的任务编号。"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from exceptions.exception import PermissionException
from module_higgsfield.service.generation_read_service import GenerationReadService


class GenerationSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_or_self_source_does_not_query(self):
        for value in (None, '0', '-1', '1', '１２', '9' * 5000, '9223372036854775808', 12):
            with self.subTest(value=str(value)[:30]), patch(
                'module_higgsfield.service.generation_read_service.GenerationReadDao.job', AsyncMock()
            ) as read:
                result = await GenerationReadService.source_job(None, None, SimpleNamespace(
                    job_id=1, project_id=7, input_snapshot={'sourceJobId': value}
                ))
                self.assertIsNone(result)
                read.assert_not_awaited()

    async def test_missing_or_other_project_source_is_hidden(self):
        for source in (None, SimpleNamespace(project_id=8)):
            with patch('module_higgsfield.service.generation_read_service.GenerationReadDao.job', AsyncMock(
                return_value=source
            )), patch('module_higgsfield.service.generation_read_service.WorkspaceService.authorize', AsyncMock()) as authorize:
                result = await GenerationReadService.source_job(None, None, SimpleNamespace(
                    job_id=1, project_id=7, input_snapshot={'sourceJobId': '12'}
                ))
                self.assertIsNone(result)
                authorize.assert_not_awaited()

    async def test_bigint_source_and_current_owner_scoped_permission(self):
        job = SimpleNamespace(job_id=1, project_id=7, input_snapshot={'sourceJobId': '9007199254740993'})
        source = SimpleNamespace(job_id=9007199254740993, project_id=7, actor_id=3)
        with patch('module_higgsfield.service.generation_read_service.GenerationReadDao.job', AsyncMock(
            return_value=source
        )), patch('module_higgsfield.service.generation_read_service.WorkspaceService.authorize', AsyncMock()) as authorize:
            self.assertEqual(await GenerationReadService.source_job('db', 'user', job), '9007199254740993')
            authorize.assert_awaited_once_with('db', 'user', 7, 'generation:read', owner_id=3)
            authorize.side_effect = PermissionException(message='来源权限已撤销')
            self.assertIsNone(await GenerationReadService.source_job('db', 'user', job))

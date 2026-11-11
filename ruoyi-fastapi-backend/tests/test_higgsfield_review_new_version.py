"""新增元素修订不能继承旧版本的审核结果。"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.review_dao import ReviewDao
from module_higgsfield.service.element_content_service import ElementContentService


class ReviewNewVersionTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_element_revision_returns_to_working_with_new_evidence(self):
        db = AsyncMock()
        user = NS(user=NS(user_id=20, user_name='制作乙'))
        element = NS(element_id=3, current_revision_id=7, work_status='3', category='character')
        content = NS(description='新版服装', is_fictional_person=True, media=[])
        with patch.object(ElementDao, 'revision', AsyncMock(return_value=NS(revision_no=1))), \
             patch.object(ElementDao, 'add', AsyncMock(return_value=NS(revision_id=8))), \
             patch.object(ReviewDao, 'record', AsyncMock()) as record:
            await ElementContentService.append(db, user, element, content, [])
            self.assertEqual(element.current_revision_id, 8)
            self.assertEqual(element.work_status, '1')
            self.assertEqual(record.await_args.kwargs['version_id'], 8)
            self.assertEqual(record.await_args.kwargs['previous'], 'approved')
            self.assertEqual(record.await_args.kwargs['action'], 'revise')

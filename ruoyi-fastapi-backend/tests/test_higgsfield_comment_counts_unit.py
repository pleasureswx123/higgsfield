"""素材评论计数的批量查询约束。"""
import unittest
from unittest.mock import AsyncMock, Mock
from sqlalchemy.dialects import postgresql
from module_higgsfield.dao.comment_dao import CommentDao


class CommentCountTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_versions_do_not_query(self):
        db = AsyncMock()
        self.assertEqual(await CommentDao.asset_version_counts(db, []), {})
        db.execute.assert_not_awaited()

    async def test_count_is_grouped_by_version_and_excludes_deleted_rows(self):
        result = Mock()
        result.all.return_value = [(7, 3), (13, 4)]
        db = AsyncMock()
        db.execute.return_value = result
        self.assertEqual(await CommentDao.asset_version_counts(db, [7, 13]), {7: 3, 13: 4})
        db.execute.assert_awaited_once()
        sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
        self.assertIn("hf_comment_thread.del_flag = '0'", sql)
        self.assertIn("hf_comment.del_flag = '0'", sql)
        self.assertIn('GROUP BY hf_comment_thread.asset_version_id', sql)
        self.assertIn('IN (7, 13)', sql)
        self.assertNotIn('parent_id IS NULL', sql)

"""评论迁移约束及边界输入，尚不证明业务授权服务已接通。"""
import importlib.util
import os
from pathlib import Path
import unittest
from decimal import Decimal
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.comment_do import HfCommentThread, HfComment, HfAnnotation
from module_higgsfield.entity.vo.comment_vo import ThreadCreate, CommentCreate, CommentPatch, Annotation
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage


class CommentInputTests(unittest.TestCase):
    def test_target_and_decimal_precision(self):
        self.assertEqual(ThreadCreate(target={'assetVersionId': '9007199254740993'}).target.asset_version_id, '9007199254740993')
        for target in ({}, {'outputId': 1}, {'outputId': '0'}, {'outputId': '1', 'assetVersionId': '2'}):
            with self.assertRaises(ValidationError):
                ThreadCreate(target=target)
        self.assertEqual(CommentCreate(body='正文', videoTime='1.000001').video_time, Decimal('1.000001'))
        for value in (True, 1.2, '-1', 'NaN', 'Infinity', '0.0000001'):
            with self.assertRaises(ValidationError):
                CommentCreate(body='正文', videoTime=value)
        for fields in ({'body': '  '}, {'body': 'a' * 5001}, {'body': '正文', 'authorId': '9'}):
            with self.assertRaises(ValidationError):
                CommentCreate(**fields)

    def test_geometry_shape_edges_and_patch_presence(self):
        base = dict(shape='point', geometry={'x': 0, 'y': 1}, color='#AABBCC', sourceWidth=200, sourceHeight=100)
        self.assertEqual(Annotation(**base).color, '#aabbcc')
        for fields in (
            {'geometry': {'x': True, 'y': 0}}, {'geometry': {'x': float('nan'), 'y': 0}},
            {'shape': 'rect', 'geometry': {'x': 0.8, 'y': 0, 'width': 0.3, 'height': 1}},
            {'shape': 'path', 'geometry': {'points': [{'x': 0, 'y': 0}]}},
            {'sourceWidth': True}, {'sourceHeight': 0}, {'color': 'url(javascript:bad)'},
            {'geometry': {'x': 0, 'y': 0, 'url': 'external'}},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Annotation(**(base | fields))
        self.assertNotIn('annotations', CommentPatch(body='修改', revision='1').model_fields_set)
        self.assertIn('annotations', CommentPatch(body='修改', revision='1', annotations=[]).model_fields_set)
        with self.assertRaises(ValidationError):
            CommentPatch(body='修改', revision='1', annotations=None)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CommentStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('comments', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_68_comments.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_real_constraints_comments_and_no_foreign_keys(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            for fields in ({}, {'output_id': 1, 'asset_version_id': 2}, {'output_id': 0}):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfCommentThread(create_user_id=1, **fields, **audit))
                        await db.flush()
            thread = HfCommentThread(output_id=9007199254740993, create_user_id=1, **audit)
            db.add(thread)
            await db.flush()
            comment = HfComment(thread_id=thread.thread_id, author_id=1, body='正文', **audit)
            db.add(comment)
            await db.flush()
            for fields in ({'video_time': -1}, {'revision': 0}, {'del_flag': '1'}, {'body': ''}):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfComment(**(dict(thread_id=thread.thread_id, author_id=1, body='正文') | fields), **audit))
                        await db.flush()
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(text('UPDATE hf_comment SET parent_id=comment_id WHERE comment_id=:id'), {'id': comment.comment_id})
            db.add(HfAnnotation(comment_id=comment.comment_id, shape='point', geometry={'x': 0, 'y': 1}, color='#ff0000', source_width=20, source_height=10, **audit))
            await db.flush()
            for table in ('hf_comment_thread', 'hf_comment', 'hf_annotation'):
                self.assertEqual(await db.scalar(text(f"SELECT count(*) FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='f'")), 0)
                self.assertEqual(await db.scalar(text(f"SELECT count(*) FROM pg_attribute WHERE attrelid='{table}'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
                self.assertTrue(await db.scalar(text(f"SELECT obj_description('{table}'::regclass,'pg_class')")))
            await db.rollback()

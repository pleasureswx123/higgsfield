"""个人偏好的输入边界与真实 PostgreSQL 迁移。"""
import importlib.util
import os
import unittest
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_higgsfield.entity.do.project_preference_do import HfProjectCollection, HfUserProjectPreference
from module_higgsfield.entity.vo.project_preference_vo import CollectionCreate, CollectionUpdate, PreferenceUpdate
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_projects as projects
from tests import test_higgsfield_job_storage as storage


class PreferenceInputTests(unittest.TestCase):
    def test_strict_patch_and_bigint(self):
        self.assertEqual(CollectionCreate(name='  制作  ').name, '制作')
        value = PreferenceUpdate(revision='0', collectionId=None)
        self.assertEqual(value.model_fields_set, {'revision', 'collection_id'})
        self.assertEqual(PreferenceUpdate(revision='1', collectionId='9007199254740993').collection_id, '9007199254740993')
        for fields in ({}, {'isPinned': None}, {'isPinned': 1}, {'isHidden': 'false'},
                       {'orderNum': True}, {'orderNum': 2147483648}, {'userId': '2'},
                       {'collectionId': 1}, {'collectionId': '9223372036854775808'}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                PreferenceUpdate(revision='0', **fields)
        for fields in ({}, {'name': None}, {'name': '  '}, {'description': '\x00'},
                       {'color': '#ABCDEF'}, {'color': 'red'}, {'orderNum': None}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                CollectionUpdate(revision='1', **fields)
        self.assertIsNone(CollectionUpdate(revision='1', color=None).color)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PreferenceStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_72_project_preferences.py'
        spec = importlib.util.spec_from_file_location('preference_migration', path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        # 项目基础测试夹具已执行真实 72 迁移，本类保留模块供降级保护验证。

    async def test_constraints_comments_and_user_scope(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            db.add_all([HfProjectCollection(user_id=user, collection_name='收藏', **audit) for user in (1, 2)])
            db.add_all([HfUserProjectPreference(user_id=user, project_id=1, **audit) for user in (1, 2)])
            await db.flush()
            cases = [
                (HfProjectCollection, dict(user_id=1, collection_name='收藏')),
                (HfProjectCollection, dict(user_id=3, collection_name=' ')),
                (HfProjectCollection, dict(user_id=3, collection_name='颜色', color='red')),
                (HfProjectCollection, dict(user_id=3, collection_name='说明', description='a' * 2001)),
                (HfUserProjectPreference, dict(user_id=1, project_id=1)),
                (HfUserProjectPreference, dict(user_id=3, project_id=0)),
                (HfUserProjectPreference, dict(user_id=3, project_id=1, revision=0)),
                (HfUserProjectPreference, dict(user_id=3, project_id=1, is_hidden='X')),
                (HfUserProjectPreference, dict(user_id=3, project_id=1, collection_id=0)),
            ]
            for model, fields in cases:
                with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(model(**fields, **audit))
                        await db.flush()
            for table in ('hf_project_collection', 'hf_user_project_preference'):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 2)
                self.assertEqual(await db.scalar(text(f"SELECT count(*) FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='f'")), 0)
                self.assertEqual(await db.scalar(text(f"SELECT count(*) FROM pg_attribute WHERE attrelid='{table}'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
                self.assertTrue(await db.scalar(text(f"SELECT obj_description('{table}'::regclass,'pg_class')")))
            await db.rollback()
        with self.assertRaises(RuntimeError):
            await self.migrate('downgrade')

"""加入申请真实迁移与输入约束，不授予项目访问权。"""
import importlib.util
import os
import unittest
from pathlib import Path
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.project_join_do import HfProjectJoinRequest
from module_higgsfield.entity.vo.project_join_vo import JoinCreate, JoinReview, JoinQuery
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_projects as projects
from tests import test_higgsfield_job_storage as storage
from utils.time_util import TimezoneUtil


class JoinInputTests(unittest.TestCase):
    def test_reason_identity_and_review_role(self):
        self.assertEqual(JoinCreate(reason='  参与制作  ').reason, '参与制作')
        self.assertIsNone(JoinCreate(reason='  ').reason)
        self.assertEqual(JoinReview(revision='1', decision='approved', roleId='9007199254740993').role_id, '9007199254740993')
        self.assertEqual(JoinReview(revision='2', decision='rejected').decision, 'rejected')
        for values in ({'userId': '2'}, {'status': 'approved'}, {'reason': 'a' * 5001}, {'reason': '\x00'}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                JoinCreate(**values)
        for values in (
            {'decision': 'approved'}, {'decision': 'rejected', 'roleId': '2'},
            {'decision': 'approved', 'roleId': 2}, {'decision': 'cancelled'},
            {'decision': 'approved', 'roleId': '9223372036854775808'},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                JoinReview(revision='1', **values)
        with self.assertRaises(ValidationError):
            JoinQuery(pageSize=101)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class JoinStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_71_project_join_requests.py'
        spec = importlib.util.spec_from_file_location('join_migration', path)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_pending_unique_review_state_and_evidence(self):
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            row = HfProjectJoinRequest(project_id=1, user_id=1, **audit)
            db.add(row); await db.flush()
            self.assertGreater(row.request_id, 0)
            for index, fields in enumerate((
                {}, {'project_id': 0}, {'revision': 0}, {'status': '9'},
                {'status': '1'}, {'status': '2', 'reviewer_id': 1},
                {'status': '3', 'reviewed_time': TimezoneUtil.utc_now()},
                {'reviewer_id': 1, 'reviewed_time': TimezoneUtil.utc_now()},
                {'reason': 'a' * 5001},
            )):
                with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfProjectJoinRequest(**(dict(project_id=1, user_id=1 if index == 0 else index + 100) | fields), **audit))
                        await db.flush()
            row.status = '2'; row.reviewer_id = 2; row.reviewed_time = TimezoneUtil.utc_now(); row.revision = 2
            await db.flush()
            db.add(HfProjectJoinRequest(project_id=1, user_id=1, **audit))
            await db.flush()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_join_request')), 2)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_project_join_request'::regclass AND contype='f'")), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_project_join_request'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL")), 0)
            self.assertTrue(await db.scalar(text("SELECT obj_description('hf_project_join_request'::regclass,'pg_class')")))
            await db.rollback()
        with self.assertRaises(RuntimeError):
            await self.migrate('downgrade')

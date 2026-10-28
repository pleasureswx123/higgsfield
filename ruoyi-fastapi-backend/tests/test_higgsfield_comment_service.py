"""评论授权、固定目标及原子创建的真实数据库验证。"""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.comment_vo import ThreadCreate, ThreadQuery, CommentCreate, CommentPage
from module_higgsfield.service.comment_service import CommentService as Service
from tests import test_higgsfield_output_asset as fixtures


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CommentServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = fixtures.OutputAssetTests.cleanup_schema
    migrate = fixtures.OutputAssetTests.migrate
    job = fixtures.OutputAssetTests.job
    output = fixtures.OutputAssetTests.output
    create = fixtures.OutputAssetTests.create
    ready = fixtures.OutputAssetTests.ready

    async def asyncSetUp(self):
        await fixtures.OutputAssetTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('comment_service_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_68_comments.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location('comment_permission_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_69_comment_permissions.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        await self.migrate('upgrade')
        async with self.sessions() as db:
            for permission in ('comment:read', 'comment:create'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM sys_menu WHERE perms=:permission'), {'permission': permission}), 1)
        await self.ready()
        async with self.sessions() as db:
            for permission in ('comment:create', 'comment:read'):
                await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"), {'permission': permission})
            await db.execute(text('UPDATE hf_stored_file SET width=128,height=64'))
            await db.commit()
        self.target = {'outputId': str(self.identity)}
        self.annotation = dict(shape='point', geometry={'x': 0.5, 'y': 0.25}, color='#ff0000', sourceWidth=128, sourceHeight=64)

    async def thread(self, key=None):
        async with self.sessions() as db:
            return await Service.create_thread(db, self.owner, ThreadCreate(target=self.target), key or str(uuid4()))

    async def post(self, identity, payload, key=None):
        async with self.sessions() as db:
            db.autoflush = False
            return await Service.create_comment(db, self.owner, identity, CommentCreate(**payload), key or str(uuid4()))

    async def test_thread_comment_reply_replay_and_revoked_read(self):
        key = str(uuid4())
        first, _ = await self.thread(key)
        again, repeated = await self.thread(key)
        self.assertTrue(repeated)
        self.assertEqual(first, again)
        thread_id = int(first['data']['id'])
        payload = dict(body='固定图片定位', annotations=[self.annotation])
        comment_key = str(uuid4())
        comment, _ = await self.post(thread_id, payload, comment_key)
        repeated_comment, replayed = await self.post(thread_id, payload, comment_key)
        self.assertTrue(replayed)
        self.assertEqual(comment, repeated_comment)
        await self.post(thread_id, dict(body='回复', parentId=comment['data']['id']))
        async with self.sessions() as db:
            page = await Service.comments(db, self.owner, thread_id, CommentPage(pageSize=1))
            self.assertEqual(page.total, 2)
            self.assertTrue(page.has_next)
            self.assertEqual(page.rows[0]['annotations'][0]['geometry'], {'x': .5, 'y': .25})
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.thread(key)
        with self.assertRaises(PermissionException):
            await self.post(thread_id, payload, comment_key)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await Service.comments(db, self.owner, thread_id, CommentPage())

    async def test_cross_thread_bad_dimensions_and_audit_failure_roll_back(self):
        one, _ = await self.thread()
        two, _ = await self.thread()
        identity = int(one['data']['id'])
        comment, _ = await self.post(identity, {'body': '第一条'})
        for thread, payload in (
            (int(two['data']['id']), dict(body='跨主题回复', parentId=comment['data']['id'])),
            (identity, dict(body='错误尺寸', annotations=[self.annotation | {'sourceWidth': 127}])),
            (identity, dict(body='图片不是视频', videoTime='0')),
        ):
            with self.assertRaises(ServiceWarning):
                await self.post(thread, payload)
        with patch.object(Service, 'audit', side_effect=RuntimeError('审计失败')):
            with self.assertRaises(RuntimeError):
                await self.post(identity, dict(body='必须回滚', annotations=[self.annotation]))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_comment')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_annotation')), 0)
            page = await Service.threads(db, self.owner, ThreadQuery(**self.target))
            self.assertEqual(page.total, 2)

    async def test_video_time_exact_boundary_and_unknown_duration(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET kind='video' WHERE output_id=:id"), {'id': self.identity})
            await db.execute(text("UPDATE hf_stored_file SET mime_type='video/mp4',seconds=1.234567 WHERE file_id=:id"), {'id': self.file_id})
            await db.commit()
        thread, _ = await self.thread()
        identity = int(thread['data']['id'])
        result, _ = await self.post(identity, dict(body='尾部定位', videoTime='1.234567'))
        self.assertEqual(result['data']['videoTime'], '1.234567')
        with self.assertRaises(ServiceWarning):
            await self.post(identity, dict(body='超出一微秒', videoTime='1.234568'))
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_stored_file SET seconds=NULL WHERE file_id=:id'), {'id': self.file_id})
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.post(identity, dict(body='未知时长不能定位', videoTime='0'))
        await self.post(identity, dict(body='未知时长仍可纯文本评论'))

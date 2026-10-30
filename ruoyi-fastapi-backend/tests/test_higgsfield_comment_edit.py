"""评论编辑、逻辑删除与治理权限的隔离数据库验证。"""
import importlib.util
import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.comment_vo import CommentPatch, CommentDelete, CommentPage
from module_higgsfield.service.comment_service import CommentService as Service
from tests import test_higgsfield_comment_service as fixture


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class CommentEditTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = fixture.CommentServiceTests.cleanup_schema
    migrate = fixture.CommentServiceTests.migrate
    job = fixture.CommentServiceTests.job
    output = fixture.CommentServiceTests.output
    create = fixture.CommentServiceTests.create
    ready = fixture.CommentServiceTests.ready
    thread = fixture.CommentServiceTests.thread
    post = fixture.CommentServiceTests.post

    async def test_status_color_survives_resolve_and_can_clear(self):
        from module_higgsfield.entity.vo.comment_vo import ThreadPatch
        async def act(revision, action, color=None):
            async with self.sessions() as db:
                result, _ = await Service.collaborate(db, self.owner, self.thread_id, ThreadPatch(revision=revision, action=action, color=color), str(uuid4()))
                return result['data']
        colored = await act('1', 'color', '#4798fa')
        self.assertEqual(colored['statusColor'], '#4798fa')
        solved = await act(colored['revision'], 'resolve')
        self.assertEqual(solved['statusColor'], '#4798fa')
        self.assertIsNotNone(solved['resolvedAt'])
        cleared = await act(solved['revision'], 'color')
        self.assertIsNone(cleared['statusColor'])
        self.assertIsNotNone(cleared['resolvedAt'])

    async def asyncSetUp(self):
        await fixture.CommentServiceTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('comment_edit_permissions', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_70_comment_edit_permissions.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        await self.migrate('upgrade')
        async with self.sessions() as db:
            for permission in ('comment:edit:own', 'comment:moderate'):
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM sys_menu WHERE perms=:p'), {'p': permission}), 1)
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'comment:edit:own','own' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"))
            await db.commit()
        thread, _ = await self.thread()
        self.thread_id = int(thread['data']['id'])
        self.create_key = str(uuid4())
        self.create_payload = dict(body='原始评论', annotations=[self.annotation])
        result, _ = await self.post(self.thread_id, self.create_payload, self.create_key)
        self.comment_id = int(result['data']['id'])

    async def edit(self, payload, key=None, delete=False):
        async with self.sessions() as db:
            db.autoflush = False
            return await Service.mutate(db, self.owner, self.comment_id,
                (CommentDelete if delete else CommentPatch)(**payload), key or str(uuid4()), delete=delete)

    async def test_annotation_presence_revision_conflict_and_rollback(self):
        first, _ = await self.edit(dict(revision='1', body='只改正文'))
        self.assertEqual(len(first['data']['annotations']), 1)
        with self.assertRaises(ServiceWarning):
            await self.edit(dict(revision='1', body='旧修订覆盖'))
        with patch.object(Service, 'audit', side_effect=RuntimeError('审计失败')):
            with self.assertRaises(RuntimeError):
                await self.edit(dict(revision='2', body='不能提交', annotations=[]))
        async with self.sessions() as db:
            row = (await Service.comments(db, self.owner, self.thread_id, CommentPage())).rows[0]
            self.assertEqual(row['body'], '只改正文')
            self.assertEqual(row['revision'], '2')
            self.assertEqual(len(row['annotations']), 1)
        cleared, _ = await self.edit(dict(revision='2', body='清空标注', annotations=[]))
        self.assertEqual(cleared['data']['annotations'], [])
        self.assertEqual(cleared['data']['revision'], '3')

    async def test_delete_preserves_replies_hides_content_and_blocks_old_create_replay(self):
        await self.post(self.thread_id, dict(body='保留回复', parentId=str(self.comment_id)))
        key = str(uuid4())
        removed, _ = await self.edit(dict(revision='1'), key, delete=True)
        replay, repeated = await self.edit(dict(revision='1'), key, delete=True)
        self.assertTrue(repeated)
        self.assertEqual(removed, replay)
        async with self.sessions() as db:
            rows = (await Service.comments(db, self.owner, self.thread_id, CommentPage())).rows
            self.assertTrue(rows[0]['deleted'])
            self.assertEqual(rows[0]['body'], '')
            self.assertIsNone(rows[0]['author'])
            self.assertEqual(rows[0]['annotations'], [])
            self.assertEqual(rows[1]['body'], '保留回复')
        with self.assertRaises(ServiceWarning):
            await self.post(self.thread_id, self.create_payload, self.create_key)
        with self.assertRaises(ServiceWarning):
            await self.post(self.thread_id, dict(body='禁止新回复', parentId=str(self.comment_id)))

    async def test_own_permission_does_not_edit_others_moderator_requires_project_scope(self):
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_comment SET author_id=999 WHERE comment_id=:id'), {'id': self.comment_id})
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.edit(dict(revision='1', body='不能编辑他人'))
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'comment:moderate','own' FROM hf_project_role WHERE code='owner'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.edit(dict(revision='1', body='本人范围不是治理'))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='project' WHERE permission_code='comment:moderate'"))
            await db.commit()
        key = str(uuid4())
        result, _ = await self.edit(dict(revision='1', body='治理修改'), key)
        self.assertEqual(result['data']['body'], '治理修改')
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='comment:moderate'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.edit(dict(revision='1', body='治理修改'), key)

    async def test_concurrent_edits_only_one_revision_wins(self):
        outcomes = await asyncio.gather(
            self.edit(dict(revision='1', body='版本甲', annotations=[])),
            self.edit(dict(revision='1', body='版本乙')),
            return_exceptions=True,
        )
        successes = [item for item in outcomes if not isinstance(item, BaseException)]
        failures = [item for item in outcomes if isinstance(item, BaseException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ServiceWarning)
        async with self.sessions() as db:
            row = (await Service.comments(db, self.owner, self.thread_id, CommentPage())).rows[0]
            self.assertEqual(row['revision'], '2')
            self.assertEqual(row['body'], successes[0][0]['data']['body'])
            self.assertEqual(len(row['annotations']), 0 if row['body'] == '版本甲' else 1)

    async def test_replace_rect_and_path_then_reject_wrong_source_size(self):
        rectangle = self.annotation | {'shape': 'rect', 'geometry': {'x': .1, 'y': .2, 'width': .3, 'height': .4}}
        path = self.annotation | {'shape': 'path', 'geometry': {'points': [{'x': 0, 'y': 1}, {'x': 1, 'y': 0}]}}
        result, _ = await self.edit(dict(revision='1', body='框选和路径', annotations=[rectangle, path]))
        self.assertEqual([item['shape'] for item in result['data']['annotations']], ['rect', 'path'])
        with self.assertRaises(ServiceWarning):
            await self.edit(dict(revision='2', body='错误尺寸不能替换', annotations=[rectangle | {'sourceHeight': 999}]))
        async with self.sessions() as db:
            row = (await Service.comments(db, self.owner, self.thread_id, CommentPage())).rows[0]
            self.assertEqual(row['revision'], '2')
            self.assertEqual(row['body'], '框选和路径')
            self.assertEqual(len(row['annotations']), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_annotation')), 2)

    async def test_reactions_resolve_reopen_and_delete_replay(self):
        from module_higgsfield.entity.vo.comment_vo import ReactionPatch, ThreadPatch
        async def act(identity, payload, key=None, reaction=False):
            async with self.sessions() as db:
                return await Service.collaborate(db, self.owner, identity, payload, key or str(uuid4()), reaction)
        key = str(uuid4())
        first, _ = await act(self.comment_id, ReactionPatch(emoji='😀', active=True), key, True)
        again, replay = await act(self.comment_id, ReactionPatch(emoji='😀', active=True), key, True)
        self.assertTrue(replay)
        self.assertEqual(first, again)
        self.assertEqual(len(first['data']['reactions']), 1)
        cancelled, _ = await act(self.comment_id, ReactionPatch(emoji='😀', active=False), reaction=True)
        self.assertEqual(cancelled['data']['reactions'], [])
        solved, _ = await act(self.thread_id, ThreadPatch(revision='1', action='resolve'))
        self.assertIsNotNone(solved['data']['resolvedAt'])
        with self.assertRaises(ServiceWarning):
            await act(self.thread_id, ThreadPatch(revision='1', action='reopen'))
        reopened, _ = await act(self.thread_id, ThreadPatch(revision='2', action='reopen'))
        self.assertIsNone(reopened['data']['resolvedAt'])
        key = str(uuid4())
        deleted, _ = await act(self.thread_id, ThreadPatch(revision='3', action='delete'), key)
        repeated, replay = await act(self.thread_id, ThreadPatch(revision='3', action='delete'), key)
        self.assertTrue(replay)
        self.assertEqual(deleted, repeated)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await Service.comments(db, self.owner, self.thread_id, CommentPage())

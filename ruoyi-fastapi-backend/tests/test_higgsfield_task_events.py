"""事件游标、重放缺口和流式授权回归。"""

import os
import unittest
from unittest.mock import patch, AsyncMock
from sqlalchemy import text
from exceptions.exception import ServiceWarning, AuthException
from module_higgsfield.service.task_event_service import TaskEventService
from module_higgsfield.entity.do.outbox_do import HfTaskEvent
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_generation_snapshot as snapshots


class EventCursorTests(unittest.TestCase):
    def test_cursor_scope_and_frame_escaping(self):
        self.assertIsNone(TaskEventService.cursor(1, None))
        self.assertEqual(TaskEventService.cursor(1, '1:9007199254740993'), 9007199254740993)
        for value in ('2:1', '1:-1', '1:01', '1:9223372036854775808', '1:2\nevent: evil'):
            with self.assertRaises(ServiceWarning):
                TaskEventService.cursor(1, value)
        frame = TaskEventService.frame('task.state', {'text': '\nevent: fake\n'})
        self.assertEqual(frame.count('\nevent:'), 0)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class TaskEventTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = snapshots.GenerationSnapshotTests.cleanup_schema
    migrate = snapshots.GenerationSnapshotTests.migrate
    job = snapshots.GenerationSnapshotTests.job
    output = snapshots.GenerationSnapshotTests.output
    create = snapshots.GenerationSnapshotTests.create
    asyncSetUp = snapshots.GenerationSnapshotTests.asyncSetUp

    async def test_initial_snapshot_replay_and_missing_history_reset(self):
        async with self.sessions() as db:
            frames, seq, visible = await TaskEventService.batch(db, self.owner, self.job_id, None)
            self.assertIn('event: task.snapshot', frames[0])
            self.assertEqual(seq, 7)
            frames, seq, _ = await TaskEventService.batch(db, self.owner, self.job_id, 3)
            self.assertIn('event: stream.reset', frames[0])
            self.assertEqual(seq, 7)
            audit = WriteService.audit(self.owner)
            db.add(
                HfTaskEvent(
                    job_id=self.job_id,
                    sequence=8,
                    event_type='task.state',
                    schema_version=1,
                    payload={
                        'revision': '9',
                        'orchestrationState': 'finished',
                        'upstreamState': 'succeeded',
                        'secret': 'private-value',
                    },
                    occurred_time=audit['create_time'],
                    **audit,
                )
            )
            await db.execute(text('UPDATE hf_creation_job SET event_sequence=8,revision=9'))
            await db.commit()
            frames, seq, _ = await TaskEventService.batch(db, self.owner, self.job_id, 7, visible)
            self.assertIn('event: task.state', frames[0])
            self.assertNotIn('private-value', frames[0])
            self.assertEqual(seq, 8)
            frames, seq, _ = await TaskEventService.batch(db, self.owner, self.job_id, 8, visible)
            self.assertEqual(frames, [])
            with self.assertRaises(ServiceWarning):
                await TaskEventService.batch(db, self.owner, self.job_id, 9)

    async def test_source_permission_loss_resets_without_task_revision(self):
        async with self.sessions() as db:
            project_id = await db.scalar(text('SELECT project_id FROM hf_creation_job WHERE job_id=:id'), {'id': self.job_id})
            source = self.job(project_id=project_id, actor_id=2, idempotency_key='source-task')
            db.add(source)
            await db.flush()
            source_id = str(source.job_id)
            await db.execute(text("UPDATE hf_creation_job SET input_snapshot=jsonb_set(input_snapshot,'{sourceJobId}',to_jsonb(CAST(:source AS text))) WHERE job_id=:id"), {'source': source_id, 'id': self.job_id})
            await db.commit()
        async with self.sessions() as db:
            frames, seq, visibility = await TaskEventService.batch(db, self.owner, self.job_id, None)
            self.assertIn(f'"sourceJobId":"{source_id}"', frames[0])
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'"))
            await db.commit()
        async with self.sessions() as db:
            frames, after_seq, after_visibility = await TaskEventService.batch(db, self.owner, self.job_id, seq, visibility)
            self.assertEqual(after_seq, seq)
            self.assertIn('event: stream.reset', frames[0])
            self.assertIn('"sourceJobId":null', frames[0])
            self.assertNotEqual(after_visibility, visibility)
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_creation_job WHERE job_id=:id'), {'id': self.job_id}), 8)

    async def test_output_permission_change_resets_and_membership_revoke_denies(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
            frames, _, visibility = await TaskEventService.batch(db, self.owner, self.job_id, 7, 'visible')
            self.assertEqual(visibility[:2], ('hidden', 'hidden'))
            self.assertIn('stream.reset', frames[0])
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await TaskEventService.batch(db, self.owner, self.job_id, 7)

    async def test_login_revocation_closes_stream_without_leaking_exception(self):
        request = type('Request', (), {'is_disconnected': AsyncMock(return_value=False)})()
        with (
            patch('module_higgsfield.service.task_event_service.DataSourceRegistry.session', self.sessions),
            patch(
                'module_higgsfield.service.task_event_service.LoginService._resolve_current_user',
                AsyncMock(side_effect=AuthException(message='private-auth-data')),
            ),
            patch('module_higgsfield.service.task_event_service.asyncio.sleep', AsyncMock()),
        ):
            stream = TaskEventService.stream(request, 'secret-token', self.job_id, 7, [], 'visible')
            messages = [item async for item in stream]
            self.assertEqual(len(messages), 2)
            self.assertIn('access.revoked', messages[-1])
            self.assertNotIn('private-auth-data', str(messages))
            self.assertNotIn('secret-token', str(messages))

    async def test_billing_permission_loss_resets_without_new_task_event(self):
        async with self.sessions() as db:
            frames, sequence, visibility = await TaskEventService.batch(
                db, self.owner, self.job_id, 7, ('visible', 'visible'))
            self.assertEqual(sequence, 7)
            self.assertEqual(visibility[:2], ('visible', 'hidden'))
            self.assertIn('event: stream.reset', frames[0])
            self.assertIn('"billingVisibility":"hidden"', frames[0])
            self.assertNotIn('"billing":', frames[0])

    async def test_hidden_output_history_uses_redacted_snapshot(self):
        async with self.sessions() as db:
            audit = WriteService.audit(self.owner)
            db.add(HfTaskEvent(
                job_id=self.job_id, sequence=8, event_type='output.state', schema_version=1,
                payload={'outputId': '987654321', 'revision': '2', 'archiveState': 'ready'},
                occurred_time=audit['create_time'], **audit,
            ))
            await db.execute(text('UPDATE hf_creation_job SET event_sequence=8'))
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
            # 重连没有前次权限信息，也不能通过旧事件读取隐藏的输出编号。
            frames, sequence, visibility = await TaskEventService.batch(db, self.owner, self.job_id, 7)
            self.assertEqual(sequence, 8)
            self.assertEqual(visibility[0], 'hidden')
            self.assertEqual(len(frames), 1)
            self.assertIn('event: stream.reset', frames[0])
            self.assertIn('"outputs":[]', frames[0])
            self.assertNotIn('987654321', frames[0])
            self.assertNotIn('event: output.state', frames[0])

    async def test_history_over_one_batch_resumes_without_duplicates(self):
        async with self.sessions() as db:
            audit = WriteService.audit(self.owner)
            for sequence in range(8, 113):
                db.add(HfTaskEvent(
                    job_id=self.job_id, sequence=sequence, event_type='task.state', schema_version=1,
                    payload={'revision': str(sequence + 1), 'upstreamState': 'running'},
                    occurred_time=audit['create_time'], **audit,
                ))
            await db.execute(text('UPDATE hf_creation_job SET event_sequence=112'))
            await db.commit()
        # 断开旧会话，按客户端保存的游标在新会话中恢复。
        async with self.sessions() as db:
            first, sequence, visibility = await TaskEventService.batch(db, self.owner, self.job_id, 7)
            self.assertEqual(len(first), 100)
            self.assertEqual(sequence, 107)
        async with self.sessions() as db:
            second, sequence, _ = await TaskEventService.batch(db, self.owner, self.job_id, sequence, visibility)
            self.assertEqual(len(second), 5)
            self.assertEqual(sequence, 112)
            ids = [frame.splitlines()[0] for frame in first + second]
            self.assertEqual(ids, [f'id: {self.job_id}:{value}' for value in range(8, 113)])
            empty, sequence, _ = await TaskEventService.batch(db, self.owner, self.job_id, sequence, visibility)
            self.assertEqual(empty, [])
            self.assertEqual(sequence, 112)

    async def test_download_permission_change_resets_without_task_revision(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET archive_state='2',file_id=:id"), {'id': self.file_id})
            await db.execute(text(
                "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) "
                "SELECT role_id,'asset:download','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM hf_project_role ON CONFLICT DO NOTHING"
            ))
            await db.commit()
            frames, sequence, visibility = await TaskEventService.batch(db, self.owner, self.job_id, None)
            self.assertIn('downloadUrl', frames[0])
            await db.commit()
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:download'"))
            await db.commit()
            frames, next_sequence, next_visibility = await TaskEventService.batch(db, self.owner, self.job_id, sequence, visibility)
            self.assertEqual(next_sequence, sequence)
            self.assertEqual(next_visibility[:2], visibility[:2])
            self.assertIn('event: stream.reset', frames[0])
            self.assertIn('previewUrl', frames[0])
            self.assertNotIn('downloadUrl', frames[0])
            self.assertIn('"revision":"8"', frames[0])
            # 断线重连只携带旧游标，没有服务端连接内的授权投影。
            reconnect, reconnect_sequence, _ = await TaskEventService.batch(db, self.owner, self.job_id, sequence)
            self.assertEqual(reconnect_sequence, sequence)
            self.assertIn('event: task.snapshot', reconnect[0])
            self.assertIn('previewUrl', reconnect[0])
            self.assertNotIn('downloadUrl', reconnect[0])
            frames, _, _ = await TaskEventService.batch(db, self.owner, self.job_id, next_sequence, next_visibility)
            self.assertEqual(frames, [])

    async def test_cancel_permission_change_resets_without_task_event(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='0',upstream_state='0',upstream_task_id=NULL,upstream_response_id=NULL"))
            await db.execute(text(
                "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) "
                "SELECT role_id,'generation:cancel','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM hf_project_role ON CONFLICT DO NOTHING"
            ))
            await db.commit()
            frames, sequence, visibility = await TaskEventService.batch(db, self.owner, self.job_id, None)
            self.assertIn('generation:cancel', frames[0])
            await db.commit()
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='generation:cancel'"))
            await db.commit()
            frames, next_sequence, _ = await TaskEventService.batch(db, self.owner, self.job_id, sequence, visibility)
            self.assertEqual(next_sequence, sequence)
            self.assertIn('event: stream.reset', frames[0])
            self.assertNotIn('generation:cancel', frames[0])

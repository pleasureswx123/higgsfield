"""隔离 PostgreSQL 的事务通知、共享监听和授权 SSE 验证，不启动生成工作器。"""
import asyncio
import os
import unittest
from contextlib import AsyncExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import AuthException
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.project_activity_notification_dao import ProjectActivityNotificationDao
from module_higgsfield.service.project_activity_hub import ProjectActivityHub
from module_higgsfield.service.project_activity_stream_service import ProjectActivityStreamService
from module_higgsfield.service.generation_activity_service import GenerationActivityService
from module_higgsfield.entity.vo.generation_query_vo import GenerationActivityQuery
from tests import test_higgsfield_generation_list as listing


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProjectActivityStreamTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = listing.GenerationListTests.cleanup_schema
    migrate = listing.GenerationListTests.migrate
    job = listing.GenerationListTests.job
    create = listing.GenerationListTests.create
    output = listing.GenerationListTests.output
    async def asyncSetUp(self):
        await listing.GenerationListTests.asyncSetUp(self)
        self.owner.user.status = '0'
        self.owner.user.del_flag = '0'

    async def ready(self, hub):
        async with asyncio.timeout(6):
            while not hub.healthy:
                await asyncio.sleep(0.02)

    async def test_twenty_subscribers_share_listener_and_commit_only_scoped_notifications(self):
        hub = ProjectActivityHub(self.engine)
        async with AsyncExitStack() as stack:
            team = [await stack.enter_async_context(hub.subscribe(self.project_id, 1, 'project')) for _ in range(20)]
            mine = await stack.enter_async_context(hub.subscribe(self.project_id, 2, 'own'))
            other = await stack.enter_async_context(hub.subscribe(999, 1, 'project'))
            await self.ready(hub)
            self.assertEqual(self.engine.pool.checkedout(), 1)
            for item in hub.subscriptions:
                item.changed.clear()
            async with self.sessions() as db:
                job = await GenerationReadDao.job(db, self.identity)
                job.event_sequence += 1
                await JobEventDao.state(db, job, job.update_time, '隔离测试', stage='references_ready')
                await asyncio.sleep(0.05)
                self.assertFalse(any(item.changed.is_set() for item in hub.subscriptions))
                await db.rollback()
            await asyncio.sleep(0.05)
            self.assertFalse(any(item.changed.is_set() for item in hub.subscriptions))
            async with self.sessions() as db:
                job = await GenerationReadDao.job(db, self.identity)
                job.event_sequence += 1
                await JobEventDao.state(db, job, job.update_time, '隔离测试', stage='references_ready')
                await db.commit()
            await asyncio.wait_for(team[0].changed.wait(), 2)
            self.assertTrue(all(item.changed.is_set() for item in team))
            self.assertFalse(mine.changed.is_set())
            self.assertFalse(other.changed.is_set())
            # 密集事件只有一个脏标记，不建立每用户无限消息队列。
            for _ in range(1000):
                hub.notify(f'{{"project":"{self.project_id}","actor":"1"}}')
            self.assertEqual(len(hub.subscriptions), 22)
        self.assertIsNone(hub.task)
        self.assertEqual(self.engine.pool.checkedout(), 0)

    async def test_stream_rechecks_membership_and_reconnects_with_sync_not_old_data(self):
        hub = ProjectActivityHub(self.engine)
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch('module_higgsfield.service.project_activity_stream_service.DataSourceRegistry.session', self.sessions), \
             patch('module_higgsfield.service.project_activity_stream_service.LoginService._resolve_current_user', AsyncMock(return_value=self.owner)):
            stream = ProjectActivityStreamService.stream(request, 'mock-token', self.project_id, 1, 'project', hub)
            try:
                first = await anext(stream)
                self.assertIn('activity.sync', first)
                self.assertNotIn('prompt', first)
                await self.ready(hub)
                async with self.sessions() as db:
                    await db.execute(text("UPDATE hf_project_member SET status='1' WHERE user_id=1"))
                    await db.commit()
                hub.invalidate()
                self.assertIn('access.revoked', await asyncio.wait_for(anext(stream), 2))
            finally:
                await stream.aclose()
            self.assertIsNone(hub.task)
            # 重连不能依赖旧连接授权，项目成员恢复后再从当前快照同步。
            denied = ProjectActivityStreamService.stream(request, 'mock-token', self.project_id, 1, 'project', hub)
            self.assertIn('access.revoked', await anext(denied))
            await denied.aclose()
            async with self.sessions() as db:
                await db.execute(text("UPDATE hf_project_member SET status='0' WHERE user_id=1"))
                await db.commit()
            restored = ProjectActivityStreamService.stream(request, 'mock-token', self.project_id, 1, 'project', hub)
            self.assertIn('activity.sync', await anext(restored))
            await restored.aclose()

    async def test_scope_downgrade_refreshes_authorized_snapshot_and_filters_other_actors(self):
        hub = ProjectActivityHub(self.engine)
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch('module_higgsfield.service.project_activity_stream_service.DataSourceRegistry.session', self.sessions), \
             patch('module_higgsfield.service.project_activity_stream_service.LoginService._resolve_current_user', AsyncMock(return_value=self.owner)):
            stream = ProjectActivityStreamService.stream(request, 'mock-token', self.project_id, 1, 'project', hub)
            try:
                await anext(stream)
                await self.ready(hub)
                async with self.sessions() as db:
                    await db.execute(text("UPDATE hf_project_member SET role_id=(SELECT role_id FROM hf_project_role WHERE code='producer') WHERE user_id=1"))
                    await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'"))
                    await db.commit()
                hub.invalidate()
                self.assertIn('activity.sync', await asyncio.wait_for(anext(stream), 2))
                subscription = next(iter(hub.subscriptions))
                self.assertEqual(subscription.scope, 'own')
                subscription.changed.clear()
                hub.notify(f'{{"project":"{self.project_id}","actor":"2"}}')
                self.assertFalse(subscription.changed.is_set())
            finally:
                await stream.aclose()

    async def test_database_listener_failure_recovers_and_invalidates_subscriptions(self):
        class FlakyEngine:
            calls = 0
            def connect(inner):
                inner.calls += 1
                if inner.calls == 1:
                    raise RuntimeError('模拟监听连接失败')
                return self.engine.connect()
        engine = FlakyEngine()
        hub = ProjectActivityHub(engine)
        async with hub.subscribe(self.project_id, 1, 'project') as subscription:
            await self.ready(hub)
            self.assertGreaterEqual(engine.calls, 2)
            self.assertTrue(subscription.changed.is_set())
        self.assertIsNone(hub.task)

    async def test_twenty_producers_across_two_projects_keep_streams_and_snapshots_isolated(self):
        from copy import deepcopy
        created, _ = await self.create(name='第二个隔离项目')
        second_project = int(created['data']['id'])
        users, projects = {}, {}
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'"))
            for index in range(20):
                actor = index + 10
                project = self.project_id if index < 10 else second_project
                user = deepcopy(self.owner)
                user.user.user_id = actor
                user.permissions = ['project:read', 'generation:read']
                users[str(actor)], projects[str(actor)] = user, project
                await db.execute(text("INSERT INTO sys_user VALUES (:id,'0','0',:name,:name)"), {'id': actor, 'name': f'模拟制作人{actor}'})
                await db.execute(text("INSERT INTO hf_project_member(project_id,user_id,role_id,joined_time,create_time,update_time) SELECT :project,:actor,role_id,NOW(),NOW(),NOW() FROM hf_project_role WHERE code='producer'"), {'project': project, 'actor': actor})
                db.add(self.job(project_id=project, actor_id=actor, idempotency_key=f'sse-actor-{actor}'))
            await db.commit()
        hub = ProjectActivityHub(self.engine)
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch('module_higgsfield.service.project_activity_stream_service.DataSourceRegistry.session', self.sessions), \
             patch('module_higgsfield.service.project_activity_stream_service.LoginService._resolve_current_user', AsyncMock(side_effect=lambda _request, token, _db, **kwargs: users[token])):
            streams = [ProjectActivityStreamService.stream(request, token, projects[token], int(token), 'project', hub) for token in users]
            try:
                frames = await asyncio.gather(*(anext(stream) for stream in streams))
                self.assertTrue(all('activity.sync' in frame for frame in frames))
                await self.ready(hub)
                self.assertEqual(len(hub.subscriptions), 20)
                self.assertEqual(self.engine.pool.checkedout(), 1)
                async def snapshot(token):
                    async with self.sessions() as db:
                        return await GenerationActivityService.read(db, users[token], GenerationActivityQuery(projectId=str(projects[token])))
                snapshots = await asyncio.gather(*(snapshot(token) for token in users))
                self.assertTrue(all(item['projectActiveCount'] == 1 and len(item['rows']) == 1 for item in snapshots))
                self.assertEqual(len({item['rows'][0]['id'] for item in snapshots}), 20)
                for item in hub.subscriptions:
                    item.changed.clear()
                hub.notify(f'{{"project":"{self.project_id}","actor":"10"}}')
                self.assertEqual([item.actor_id for item in hub.subscriptions if item.changed.is_set()], [10])
                async with self.sessions() as db:
                    await db.execute(text("UPDATE hf_project_member SET status='1' WHERE user_id=10"))
                    await db.commit()
                self.assertIn('access.revoked', await asyncio.wait_for(anext(streams[0]), 3))
            finally:
                await asyncio.gather(*(stream.aclose() for stream in streams))
        self.assertIsNone(hub.task)


class ProjectStreamFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_stream_rechecks_auth_and_periodically_requests_snapshot_without_notifications(self):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def session():
            yield object()
        class SilentHub(ProjectActivityHub):
            async def listen(self):
                self.healthy = True
                await asyncio.Event().wait()
        user = SimpleNamespace(user=SimpleNamespace(user_id=1))
        hub = SilentHub()
        request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
        with patch('module_higgsfield.service.project_activity_stream_service.DataSourceRegistry.session', session), \
             patch('module_higgsfield.service.project_activity_stream_service.LoginService._resolve_current_user', AsyncMock(side_effect=[user, user, AuthException(message='过期')])) as login, \
             patch.object(ProjectActivityStreamService, 'authorize', AsyncMock(return_value='project')), \
             patch.object(ProjectActivityStreamService, 'CHECK_SECONDS', 0.001), \
             patch.object(ProjectActivityStreamService, 'SYNC_SECONDS', 0):
            stream = ProjectActivityStreamService.stream(request, 'mock', 1, 1, 'project', hub)
            try:
                self.assertIn('activity.sync', await anext(stream))
                self.assertIn('activity.sync', await asyncio.wait_for(anext(stream), 3))
                self.assertIn('access.revoked', await asyncio.wait_for(anext(stream), 3))
                self.assertEqual(login.await_count, 3)
            finally:
                await stream.aclose()
        self.assertIsNone(hub.task)

    async def test_login_expiry_and_service_failure_are_distinct_and_release_subscription(self):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def session():
            yield object()
        class SilentHub(ProjectActivityHub):
            async def listen(self):
                await asyncio.Event().wait()
        for error, expected in ((AuthException(message='登录失效'), 'access.revoked'), (RuntimeError('数据库暂不可用'), 'activity.degraded')):
            hub = SilentHub()
            with patch('module_higgsfield.service.project_activity_stream_service.DataSourceRegistry.session', session), \
                 patch('module_higgsfield.service.project_activity_stream_service.LoginService._resolve_current_user', AsyncMock(side_effect=error)):
                request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
                stream = ProjectActivityStreamService.stream(request, 'mock', 1, 1, 'project', hub)
                frame = await anext(stream)
                self.assertIn(expected, frame)
                self.assertNotIn('数据库暂不可用', frame)
                self.assertNotIn('登录失效', frame)
                await stream.aclose()
                self.assertIsNone(hub.task)

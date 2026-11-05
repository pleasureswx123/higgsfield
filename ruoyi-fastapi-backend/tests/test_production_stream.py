"""多人订阅时稳定状态轻量读取，并按时重验对象授权。"""
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.task_event_service import TaskEventService


class ProductionStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_stable_stream_reduces_snapshots_but_rechecks_permissions(self):
        tick = [0]

        @asynccontextmanager
        async def session():
            yield object()

        async def sleep(_):
            tick[0] += 1

        marker = SimpleNamespace(event_sequence=7)
        request = SimpleNamespace(is_disconnected=AsyncMock(side_effect=lambda: tick[0] >= 12))
        user = SimpleNamespace(user=SimpleNamespace(status='0', del_flag='0'))
        batch = AsyncMock(return_value=([], 7, None))
        with patch('module_higgsfield.service.task_event_service.DataSourceRegistry.session', session), \
             patch('module_higgsfield.service.task_event_service.LoginService._resolve_current_user', AsyncMock(return_value=user)) as login, \
             patch('module_higgsfield.service.task_event_service.TaskEventDao.watermark', AsyncMock(return_value=marker)), \
             patch.object(TaskEventService, 'batch', batch), \
             patch('module_higgsfield.service.task_event_service.time.monotonic', lambda: tick[0]), \
             patch('module_higgsfield.service.task_event_service.asyncio.sleep', sleep):
            _ = [frame async for frame in TaskEventService.stream(request, 'mock', 1, 7, [], None)]
        self.assertEqual(login.await_count, 12)
        self.assertEqual(batch.await_count, 3)

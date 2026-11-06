"""每个 API 进程共用一个数据库监听连接；订阅只保存有界脏标记，不缓存用户数据。"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from sqlalchemy import text
from config.database import DataSourceRegistry


@dataclass(eq=False)
class ActivitySubscription:
    project_id: int
    actor_id: int
    scope: str
    changed: asyncio.Event = field(default_factory=asyncio.Event)


class ProjectActivityHub:
    def __init__(self, engine=None):
        self.engine = engine
        self.subscriptions = set()
        self.task = None
        self.healthy = False

    def notify(self, payload):
        try:
            data = json.loads(payload)
            project, actor = int(data['project']), int(data['actor'])
        except (ValueError, TypeError, KeyError):
            return
        for item in self.subscriptions:
            if item.project_id == project and (item.actor_id == actor or (item.scope == 'project' and not data.get('ownOnly'))):
                item.changed.set()

    def invalidate(self):
        for item in self.subscriptions:
            item.changed.set()

    @asynccontextmanager
    async def subscribe(self, project_id, actor_id, scope):
        item = ActivitySubscription(project_id, actor_id, scope)
        self.subscriptions.add(item)
        if self.task is None:
            self.task = asyncio.create_task(self.listen())
        try:
            yield item
        finally:
            self.subscriptions.discard(item)
            if not self.subscriptions:
                await self.close()

    async def close(self):
        task, self.task = self.task, None
        self.healthy = False
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def listen(self):
        while True:
            try:
                engine = self.engine or DataSourceRegistry.get_async_engine()
                async with engine.connect() as connection:
                    raw = await connection.get_raw_connection()
                    driver = raw.driver_connection
                    channel = await connection.scalar(text("SELECT 'hf_activity_' || md5(current_schema())"))
                    await connection.rollback()
                    def notified(_connection, _pid, _channel, payload):
                        self.notify(payload)
                    await driver.add_listener(channel, notified)
                    self.healthy = True
                    # 先监听再补查，覆盖启动、重连及通知丢失期间的状态变化。
                    self.invalidate()
                    try:
                        while True:
                            await asyncio.sleep(5)
                            await connection.execute(text('SELECT 1'))
                            await connection.rollback()
                    finally:
                        self.healthy = False
                        if not driver.is_closed():
                            await driver.remove_listener(channel, notified)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.healthy = False
                self.invalidate()
                logging.getLogger(__name__).warning('项目通知监听重连：%s', type(error).__name__)
                await asyncio.sleep(2)


project_activity_hub = ProjectActivityHub()

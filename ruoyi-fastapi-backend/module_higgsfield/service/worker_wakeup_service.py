"""数据库通知仅用于唤醒；任务表与定时补查仍是执行依据。"""
import asyncio
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy import text

current_wakeup = ContextVar('worker_wakeup', default=None)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def worker_notifications(engine, stop):
    wakeup = asyncio.Event()
    token = current_wakeup.set(wakeup)

    async def listen():
        while not stop.is_set():
            try:
                # 独占连接，不与业务事务共享；asyncpg 的监听注册立即完成。
                async with engine.connect() as connection:
                    raw = await connection.get_raw_connection()
                    driver = raw.driver_connection
                    channel = await connection.scalar(text("SELECT 'hf_generation_ready_' || md5(current_schema())"))
                    await connection.rollback()

                    def notified(*_):
                        wakeup.set()

                    await driver.add_listener(channel, notified)
                    wakeup.set()  # 先监听再补查，覆盖启动与重连期间提交的任务。
                    try:
                        while not stop.is_set():
                            await connection.execute(text('SELECT 1'))
                            await connection.rollback()
                            try:
                                await asyncio.wait_for(stop.wait(), 5)
                            except TimeoutError:
                                pass
                    finally:
                        if not driver.is_closed():
                            await driver.remove_listener(channel, notified)
            except Exception as error:
                logger.warning('工作器通知连接暂不可用，将重连并补查：%s', type(error).__name__)
                try:
                    await asyncio.wait_for(stop.wait(), 2)
                except TimeoutError:
                    pass

    task = asyncio.create_task(listen())
    try:
        yield wakeup
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        current_wakeup.reset(token)

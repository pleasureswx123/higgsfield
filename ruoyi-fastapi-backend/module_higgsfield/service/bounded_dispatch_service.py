"""保持并发上限，空闲名额及时补位；停止时等待在途任务完成。"""
import asyncio
import logging
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError as PoolTimeoutError
from module_higgsfield.service.worker_wakeup_service import current_wakeup


async def serve_bounded(stop, capacity, claim, execute, *, wakeup=None, poll_seconds=1):
    wakeup = wakeup if wakeup is not None else current_wakeup.get()
    pending = set()
    stopping = asyncio.create_task(stop.wait())
    retry_at = 0.0
    loop = asyncio.get_running_loop()
    try:
        while not stop.is_set():
            if len(pending) < capacity and loop.time() >= retry_at:
                if wakeup is not None:
                    wakeup.clear()  # 在查询前清除，查询期间到达的通知不能丢失。
                try:
                    items = await claim(capacity - len(pending))
                except (OperationalError, InterfaceError, PoolTimeoutError, OSError) as error:
                    # 连接故障只延后领取，不取消其他在途任务，也不记录可能含凭据的异常正文。
                    logging.getLogger(__name__).warning('任务领取连接暂不可用，将重试：%s', type(error).__name__)
                    retry_at = loop.time() + max(1, poll_seconds)
                else:
                    pending.update(asyncio.create_task(execute(item)) for item in items)
            notification = (asyncio.create_task(wakeup.wait())
                            if wakeup is not None and len(pending) < capacity and loop.time() >= retry_at else None)
            try:
                done, _ = await asyncio.wait(pending | {stopping} | ({notification} if notification else set()),
                                             timeout=poll_seconds, return_when=asyncio.FIRST_COMPLETED)
            finally:
                if notification is not None:
                    notification.cancel()
                    await asyncio.gather(notification, return_exceptions=True)
            for task in done & pending:
                pending.remove(task)
                task.result()
        if pending:
            await asyncio.gather(*pending)
    finally:
        stopping.cancel()
        for task in pending:
            task.cancel()
        await asyncio.gather(stopping, *pending, return_exceptions=True)

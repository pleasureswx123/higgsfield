"""保持并发上限，空闲名额及时补位；停止时等待在途任务完成。"""
import asyncio


async def serve_bounded(stop, capacity, claim, execute):
    pending = set()
    stopping = asyncio.create_task(stop.wait())
    try:
        while not stop.is_set():
            if len(pending) < capacity:
                items = await claim(capacity - len(pending))
                pending.update(asyncio.create_task(execute(item)) for item in items)
            done, _ = await asyncio.wait(pending | {stopping}, timeout=1, return_when=asyncio.FIRST_COMPLETED)
            for task in done - {stopping}:
                pending.remove(task)
                task.result()
        if pending:
            await asyncio.gather(*pending)
    finally:
        stopping.cancel()
        for task in pending:
            task.cancel()
        await asyncio.gather(stopping, *pending, return_exceptions=True)

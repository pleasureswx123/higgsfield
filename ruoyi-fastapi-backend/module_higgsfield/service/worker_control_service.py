"""本地工作器协作停机与健康心跳，不对外开放监听端口。"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text


async def serve_controlled(worker, engine, stop, *, control_dir=None, mode='', concurrency=1, drain_seconds=60):
    directory = Path(control_dir) if control_dir else None
    if directory:
        directory.mkdir(parents=True, exist_ok=True)
    state = 'starting'

    def report(database_ready):
        if directory:
            temporary = directory / 'status.tmp'
            temporary.write_text(json.dumps({
                'pid': os.getpid(), 'mode': mode, 'concurrency': concurrency,
                'state': state, 'databaseReady': database_ready,
                'updatedAt': datetime.now(timezone.utc).isoformat(),
            }), encoding='utf-8')
            temporary.replace(directory / 'status.json')

    async def monitor():
        nonlocal state
        while True:
            if directory and (directory / 'stop').exists():
                stop.set()
            ready = False
            try:
                async with asyncio.timeout(3):
                    async with engine.connect() as connection:
                        await connection.execute(text('SELECT 1'))
                ready = True
            except Exception:
                pass
            state = 'draining' if stop.is_set() else ('ready' if ready else 'database_unavailable')
            report(ready)
            await asyncio.sleep(1)

    execution = asyncio.create_task(worker.serve(stop))
    monitoring = asyncio.create_task(monitor())
    stopping = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait({execution, monitoring, stopping}, return_when=asyncio.FIRST_COMPLETED)
        if monitoring in done:
            await monitoring
        if execution not in done:
            state = 'draining'
            report(False)
            try:
                await asyncio.wait_for(asyncio.shield(execution), drain_seconds)
            except TimeoutError:
                state = 'drain_timeout'
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                raise RuntimeError('安全停机等待超时，在途请求按既有租约恢复规则处理') from None
        await execution
        state = 'stopped'
    except BaseException:
        if state != 'drain_timeout':
            state = 'failed'
        raise
    finally:
        for task in (execution, monitoring, stopping):
            task.cancel()
        await asyncio.gather(execution, monitoring, stopping, return_exceptions=True)
        report(False)

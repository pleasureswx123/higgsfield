"""在事件循环外打开和关闭受控存储文件。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import BinaryIO

from module_higgsfield.service.storage_service import StorageService


@asynccontextmanager
async def open_source(storage: StorageService, key: str, *, write: bool = False) -> AsyncIterator[BinaryIO]:
    manager = storage.open_key(key, write=write)
    opening = asyncio.create_task(asyncio.to_thread(manager.__enter__))
    try:
        handle = await asyncio.shield(opening)
    except asyncio.CancelledError:
        await opening
        await asyncio.to_thread(manager.__exit__, None, None, None)
        raise
    try:
        yield handle
    finally:
        await asyncio.to_thread(manager.__exit__, None, None, None)

"""仅在强ETag和精确范围校验下下载分段，连接中断时续传当前分段。"""

import asyncio
import re

import httpx


def range_facts(response):
    value = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('content-range', ''))
    if response.status_code != 206 or value is None:
        raise ValueError('下载范围响应无效')
    start, end, total = map(int, value.groups())
    if not 0 <= start <= end < total:
        raise ValueError('下载范围边界无效')
    return start, end, total


def strong_etag(response):
    value = response.headers.get('etag', '')
    return value if re.fullmatch(r'"[^"\r\n]+"', value) else None


async def write_at(handle, lock, offset, data):
    """同一文件的定位写不可交错；取消时等待正在执行的写入结束。"""
    def write():
        handle.seek(offset)
        handle.write(data)

    async with lock:
        task = asyncio.create_task(asyncio.to_thread(write))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise


async def download_ranges(transport, request, handle, total, etag, concurrency, progress, metrics):
    lock = asyncio.Lock()
    sizes = [0] * concurrency
    width = (total + concurrency - 1) // concurrency

    async def part(index):
        start, end = index * width, min(total, (index + 1) * width) - 1
        if start > end:
            return
        cursor = start
        for attempt in range(3):
            response = None
            try:
                metrics['requests'] += 1
                response = await transport.handle_async_request(request({
                    'Range': f'bytes={cursor}-{end}', 'If-Range': etag,
                }))
                if (response.headers.get('content-encoding', 'identity').lower() != 'identity'
                        or strong_etag(response) != etag
                        or range_facts(response) != (cursor, end, total)):
                    raise ValueError('分段下载的文件标识或范围发生变化')
                length = response.headers.get('content-length')
                if length is not None and int(length) != end - cursor + 1:
                    raise ValueError('分段下载长度不匹配')
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if cursor + len(chunk) > end + 1:
                        raise ValueError('分段下载超出请求范围')
                    await write_at(handle, lock, cursor, chunk)
                    cursor += len(chunk)
                    sizes[index] = cursor - start
                    metrics['receivedBytes'] += len(chunk)
                    await progress(sum(sizes), total)
                if cursor != end + 1:
                    raise httpx.RemoteProtocolError('分段下载提前结束')
                return
            except httpx.TransportError:
                # 范围字节已完整落盘时，不再发送 start>end 的无效续传请求。
                # 文件标识、范围及长度已验证，最终仍须执行整文件媒体校验。
                if cursor == end + 1:
                    return
                if attempt == 2:
                    raise
                metrics['resumeCount'] += 1
            finally:
                if response is not None:
                    await response.aclose()

    tasks = [asyncio.create_task(part(i)) for i in range(concurrency)]
    try:
        await asyncio.gather(*tasks)
    finally:
        # 一个分段失败时取消并等待其他分段退出，再关闭或删除当前临时文件。
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

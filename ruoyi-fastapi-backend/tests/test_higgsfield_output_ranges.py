"""真实回环HTTP验证范围拼接、断线续传和错误清理；媒体解码另由原下载与真实成片测试覆盖。"""
import asyncio
import hashlib
import re
import tempfile
import unittest
import httpx
from pathlib import Path
from unittest.mock import Mock
from dataclasses import replace

from module_higgsfield.service.output_download_service import OutputDownloadPolicy, OutputDownloadService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class OutputRangeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = bytes(range(256)) * 8192
        self.storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 3_000_000, 10000))
        self.storage.verify_media = Mock(return_value={'mime_type': 'video/mp4', 'width': 16, 'height': 8, 'seconds': 30})
        self.requests, self.active, self.peak, self.dropped = [], 0, 0, False
        self.mode = 'normal'
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.policy = OutputDownloadPolicy(('127.0.0.1',), 3_000_000, allowed_ports=(self.port,), local_test=True)
        self.url = f'http://127.0.0.1:{self.port}/media?signature=secret'

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def respond(self, reader, writer):
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            raw = (await reader.readuntil(b'\r\n\r\n')).decode()
            self.requests.append(raw)
            match = re.search(r'Range: bytes=(\d+)-(\d+)', raw)
            partial = match is not None and self.mode != 'ignore'
            start, end = map(int, match.groups()) if partial else (0, len(self.data) - 1)
            probe = partial and end == 0
            etag = 'W/"file"' if self.mode == 'weak' else '"file"'
            if self.mode == 'changed' and partial and not probe:
                etag = '"changed"'
            shown_start = start + 1 if self.mode == 'wrong_range' and not probe else start
            headers = f'ETag: {etag}\r\nContent-Length: {end-start+1}\r\n'
            if self.mode == 'drop_after_complete' and not probe:
                headers = f'ETag: {etag}\r\nTransfer-Encoding: chunked\r\n'
            if partial:
                headers += f'Content-Range: bytes {shown_start}-{end}/{len(self.data)}\r\n'
            writer.write(f'HTTP/1.1 {"206 Partial Content" if partial else "200 OK"}\r\n{headers}Connection: close\r\n\r\n'.encode())
            await writer.drain()
            if not probe:
                await asyncio.sleep(0.03)
            if self.mode == 'drop_after_complete' and partial and not probe:
                # 全部范围字节已发送，但故意缺少HTTP分块传输的结束块。
                body = self.data[start:end+1]
                writer.write(f'{len(body):x}\r\n'.encode() + body + b'\r\n')
            elif self.mode in {'drop', 'drop_always'} and partial and not probe and (not self.dropped or self.mode == 'drop_always'):
                self.dropped = True
                writer.write(self.data[start:start+65536])
            else:
                writer.write(self.data[start:end+1])
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.active -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def download(self):
        self.progress = []
        async def record(value):
            self.progress.append(dict(value))
        return await OutputDownloadService(self.storage, self.policy).download(self.url, kind='video', progress=record)

    async def test_parallel_content_matches_and_has_bounded_progress(self):
        result = await self.download()
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((Path(self.temp.name) / result['storage_key']).read_bytes(), self.data)
        self.assertGreater(self.peak, 1)
        self.assertLessEqual(self.peak, 4)
        self.assertEqual(len(self.requests), 5)
        self.assertTrue(all('If-Range: "file"' in r for r in self.requests[1:]))
        self.assertEqual(self.progress[-1]['bytes'], len(self.data))
        self.assertEqual(self.progress[-1]['stage'], 'complete')
        self.assertNotIn('signature', str(self.progress))

    async def test_disconnect_resumes_only_remaining_part(self):
        self.mode = 'drop'
        result = await self.download()
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(self.progress[-1]['resumeCount'], 1)
        self.assertEqual(len(self.requests), 6)
        self.assertTrue(any('Range: bytes=65536-524287' in r for r in self.requests))

    async def test_ignored_range_and_weak_etag_fall_back_to_whole_file(self):
        for mode, count in [('ignore', 1), ('weak', 2)]:
            self.mode, self.requests = mode, []
            result = await self.download()
            self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
            self.assertEqual(len(self.requests), count)
            self.assertEqual(self.progress[-1]['connections'], 1)

    async def test_complete_range_does_not_resume_past_end_after_disconnect(self):
        self.mode = 'drop_after_complete'
        result = await self.download()
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual(len(self.requests), 5)
        self.assertEqual(self.progress[-1]['resumeCount'], 0)

    async def test_repeated_disconnect_is_bounded_and_cleans_partial_file(self):
        self.mode = 'drop_always'
        with self.assertRaises(httpx.TransportError):
            await self.download()
        self.assertLessEqual(len(self.requests), 13)
        self.assertEqual([p for p in Path(self.temp.name).rglob('*') if p.is_file()], [])
        self.storage.verify_media.assert_not_called()

    async def test_changed_validator_bad_range_and_size_are_not_published(self):
        for mode in ['changed', 'wrong_range', 'oversize']:
            self.mode = mode
            self.policy = replace(self.policy, max_bytes=10 if mode == 'oversize' else 3_000_000)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                await self.download()
            self.assertEqual([p for p in Path(self.temp.name).rglob('*') if p.is_file()], [])
        self.storage.verify_media.assert_not_called()

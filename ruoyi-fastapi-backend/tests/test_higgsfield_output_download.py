"""回环HTTP下载、真实图片校验、失败清理及下载网络边界。"""

import asyncio
import hashlib
import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from exceptions.exception import ServiceWarning
from module_higgsfield.service.output_download_service import OutputDownloadPolicy, OutputDownloadService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class OutputDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 100000, 10000))
        buffer = io.BytesIO()
        Image.new('RGB', (16, 8), 'blue').save(buffer, format='PNG')
        self.data = buffer.getvalue()
        self.mode, self.requests = 'ok', []
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0)
        self.port = self.server.sockets[0].getsockname()[1]
        self.policy = OutputDownloadPolicy(('127.0.0.1',), 100000, allowed_ports=(self.port,), local_test=True)
        self.url = f'http://127.0.0.1:{self.port}/output?signature=secret'
        self.downloader = OutputDownloadService(self.storage, self.policy)

    async def asyncTearDown(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            self.requests.append(await reader.readuntil(b'\r\n\r\n'))
            status, extra, body = '200 OK', '', self.data
            if self.mode == 'redirect':
                status, extra = '302 Found', f'Location: {self.url}\r\n'
            if self.mode == 'invalid':
                body = b'<html>not an image</html>'
            writer.write(
                f'HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n'.encode() + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_download_decodes_real_image_and_hashes_file(self) -> None:
        result = await self.downloader.download(self.url, kind='image')
        self.assertEqual(result['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((result['width'], result['height'], result['mime_type']), (16, 8, 'image/png'))
        actual = await asyncio.to_thread((Path(self.temp.name) / result['storage_key']).read_bytes)
        self.assertEqual(actual, self.data)
        self.assertNotIn(b'Authorization:', self.requests[0])

    async def test_invalid_large_and_redirect_responses_do_not_leave_files(self) -> None:
        for mode in ('invalid', 'redirect', 'large'):
            self.mode = mode
            policy = replace(self.policy, max_bytes=10) if mode == 'large' else self.policy
            expected_error = ServiceWarning if mode == 'invalid' else ValueError
            with self.subTest(mode=mode), self.assertRaises(expected_error):
                await OutputDownloadService(self.storage, policy).download(self.url, kind='image')
        files = await asyncio.to_thread(lambda: list(Path(self.temp.name).rglob('*')))
        self.assertEqual([p for p in files if p.is_file()], [])
        self.assertEqual(len(self.requests), 3)

    async def test_public_mode_rejects_loopback_and_unapproved_hosts(self) -> None:
        downloader = OutputDownloadService(self.storage, replace(self.policy, local_test=False))
        for url in (self.url, self.url.replace('http:', 'https:'), 'https://unapproved.example/file'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await downloader.target(url)
        self.assertEqual(self.requests, [])

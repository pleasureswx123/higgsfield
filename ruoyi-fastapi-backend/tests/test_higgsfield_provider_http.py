"""真实HTTP客户端访问回环模拟服务，验证传输限制且不调用供应商。"""

import asyncio
import hashlib
import io
import unittest
from dataclasses import asdict

from pydantic import SecretStr

from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion
from module_higgsfield.entity.vo.provider_vo import ConnectionFields
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService, CredentialKeyring
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.provider_upload_stream import ProviderUploadStream


class ProviderHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests = []
        self.tasks = set()
        self.mode = 'ok'
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0)
        port = self.server.sockets[0].getsockname()[1]
        self.connection = ConnectionFields(
            name='本地模拟',
            baseUrl=f'http://127.0.0.1:{port}/gateway',
            adapterVersion='videoplus-v1',
            config={
                'allowedHosts': ['127.0.0.1'],
                'connectTimeoutSeconds': 1,
                'readTimeoutSeconds': 1,
                'operationTimeoutSeconds': 1,
                'taskTimeoutSeconds': 60,
            },
        )
        self.client = ProviderHttpService(self.connection, SecretStr('test-secret-value'), max_response_bytes=1024)

    async def asyncTearDown(self) -> None:
        self.server.close()
        await self.server.wait_closed()
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def respond(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            header = await reader.readuntil(b'\r\n\r\n')
            lines = header.decode('ascii').split('\r\n')
            headers = dict(line.split(': ', 1) for line in lines[1:] if ': ' in line)
            body = await reader.readexactly(int(headers.get('Content-Length', '0')))
            self.requests.append((lines[0], headers, body))
            status, extra, data = '200 OK', '', b'{"id":"response"}'
            if self.mode == 'timeout':
                await asyncio.sleep(3)
            elif self.mode == 'redirect':
                status, extra = '307 Temporary Redirect', 'Location: http://127.0.0.1:1/leak\r\n'
            elif self.mode == 'html':
                status, data = '500 Internal Server Error', b'<html>gateway failure</html>'
            elif self.mode == 'large':
                data = b'x' * 2048
            elif self.mode == 'duplicate':
                data = b'{"id":"one","id":"two"}'
            writer.write(
                (f'HTTP/1.1 {status}\r\nContent-Length: {len(data)}\r\n{extra}Connection: close\r\n\r\n').encode()
                + data
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            self.tasks.discard(task)

    async def test_real_http_headers_paths_and_redacted_result(self) -> None:
        result = await self.client.submit({'model': 'test', 'messages': []})
        self.assertEqual((result.transport, result.http_status), ('response', 200))
        self.assertEqual(result.body, {'id': 'response'})
        self.assertNotIn('response"', repr(result))
        request, headers, body = self.requests[0]
        self.assertEqual(request, 'POST /gateway/v1/chat/completions HTTP/1.1')
        self.assertEqual(headers['Authorization'], 'Bearer test-secret-value')
        self.assertEqual(headers['X-Biz-Id'], 'op')
        self.assertIn(b'"model":"test"', body)
        await self.client.poll('task:1')
        self.assertEqual(self.requests[1][0], 'GET /gateway/v1/video/tasks/task%3A1 HTTP/1.1')

    async def test_redirect_error_size_and_duplicate_json_are_not_retried(self) -> None:
        for mode, issue in (
            ('redirect', None),
            ('html', 'RESPONSE_JSON_INVALID'),
            ('large', 'RESPONSE_TOO_LARGE'),
            ('duplicate', 'RESPONSE_JSON_INVALID'),
        ):
            self.mode = mode
            before = len(self.requests)
            result = await self.client.submit({'model': 'test'})
            self.assertEqual(len(self.requests), before + 1)
            self.assertEqual(result.issue, issue)
            if mode == 'redirect':
                self.assertEqual(result.http_status, 307)

    async def test_timeout_returns_unknown_transport_once(self) -> None:
        self.mode = 'timeout'
        result = await self.client.submit({'model': 'test'})
        self.assertEqual(result.transport, 'timeout')
        self.assertIsNone(result.http_status)
        self.assertIsNone(result.body)
        self.assertEqual(len(self.requests), 1)

    async def test_upload_sends_real_multipart_stream_once(self) -> None:
        content = b'\x89PNG\r\n\x00\xff' * 10000
        upload = ProviderUploadStream(
            io.BytesIO(content),
            file_name='reference.png',
            mime_type='image/png',
            byte_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            max_bytes=200000,
        )
        result = await self.client.upload(upload)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(len(self.requests), 1)
        request, headers, body = self.requests[0]
        self.assertEqual(request, 'POST /gateway/v1/assets/upload HTTP/1.1')
        self.assertEqual(headers['Content-Type'], upload.content_type)
        self.assertEqual(int(headers['Content-Length']), upload.content_length)
        self.assertEqual(body, upload.prefix + content + upload.suffix)

    async def test_fixed_versions_decrypt_and_reject_different_connection(self) -> None:
        crypto = CredentialCryptoService(CredentialKeyring('test', {'test': b'a' * 32}, b'b' * 32))
        encrypted = crypto.encrypt('test-secret-value', 10, 20, 1)
        credential = HfCredentialVersion(
            credential_id=10,
            connection_version_id=20,
            version_no=1,
            **asdict(encrypted),
        )
        connection = HfProviderConnectionVersion(
            connection_version_id=20,
            base_url=self.connection.base_url,
            adapter_version=self.connection.adapter_version,
            config=self.connection.config.model_dump(by_alias=True),
        )
        client = ProviderHttpService.from_versions(connection, credential, crypto=crypto)
        result = await client.poll('fixed-task')
        self.assertEqual(result.http_status, 200)
        self.assertEqual(self.requests[0][1]['Authorization'], 'Bearer test-secret-value')
        connection.connection_version_id = 21
        with self.assertRaises(ValueError):
            ProviderHttpService.from_versions(connection, credential, crypto=crypto)

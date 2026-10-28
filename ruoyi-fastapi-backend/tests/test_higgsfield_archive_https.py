"""真实TLS、图片文件及隔离PostgreSQL贯通归档，不替换HTTP或下载实现。"""

import asyncio
import hashlib
import io
import os
import ssl
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image
from sqlalchemy import text

from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.output_archive_worker import OutputArchiveWorker
from module_higgsfield.service.output_download_service import OutputDownloadPolicy, OutputDownloadService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from tests import test_higgsfield_output_archive as archive


def certificates(folder):
    """仅在临时目录生成测试证书；证书只匹配localhost，不匹配连接IP。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    (folder / 'cert.pem').write_bytes(pem)
    (folder / 'key.pem').write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(folder / 'cert.pem', folder / 'key.pem')
    client = ssl.create_default_context(cadata=pem.decode())
    return server, client


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ArchiveHttpsTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = archive.OutputArchiveTests.cleanup_schema
    migrate = archive.OutputArchiveTests.migrate
    output = archive.OutputArchiveTests.output
    job = archive.OutputArchiveTests.job

    async def asyncSetUp(self):
        await archive.OutputArchiveTests.asyncSetUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        server_context, self.client_context = await asyncio.to_thread(certificates, root)
        self.sni, self.requests = [], []
        server_context.set_servername_callback(lambda sock, name, context: self.sni.append(name))
        self.delay = 0
        buffer = io.BytesIO()
        Image.new('RGB', (24, 12), 'green').save(buffer, format='PNG')
        self.data = buffer.getvalue()
        self.server = await asyncio.start_server(self.respond, '127.0.0.1', 0, ssl=server_context)
        self.addAsyncCleanup(self.close_server)
        self.port = self.server.sockets[0].getsockname()[1]
        self.storage = StorageService(StoragePolicy(str(root / 'media-root'), 'local-test', '', 100000, 10000))
        await asyncio.to_thread((root / 'media-root').mkdir)
        self.crypto = OutputSourceCryptoService(CredentialKeyring('v1', {'v1': b'x' * 32}, b'y' * 32))
        self.downloader = OutputDownloadService(
            self.storage,
            OutputDownloadPolicy(
                ('localhost', '127.0.0.1'),
                100000,
                allowed_ports=(self.port,),
                local_test=True,
            ),
        )
        self.worker = OutputArchiveWorker(self.sessions, 'tls-archiver', self.downloader, self.crypto, lease_seconds=5)
        await self.source('localhost')

    async def source(self, hostname):
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, self.identity)
            output.source_url_ciphertext = self.crypto.encrypt(
                f'https://{hostname}:{self.port}/image?signature=private',
                output.job_id,
                output.ordinal,
            )
            await db.commit()

    async def close_server(self):
        self.server.close()
        await self.server.wait_closed()

    async def respond(self, reader, writer):
        try:
            self.requests.append(await reader.readuntil(b'\r\n\r\n'))
            await asyncio.sleep(self.delay)
            writer.write(
                f'HTTP/1.1 200 OK\r\nContent-Length: {len(self.data)}\r\nConnection: close\r\n\r\n'.encode() + self.data
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    def trusted_transport(self):
        # 只注入测试CA，仍由真实httpx/httpcore连接并校验证书、主机名和SNI。
        transport = httpx.AsyncHTTPTransport
        return patch(
            'httpx.AsyncHTTPTransport', side_effect=lambda **kwargs: transport(verify=self.client_context, **kwargs)
        )

    async def test_https_archive_survives_initial_lease_and_preserves_bytes(self):
        self.delay = 6
        with self.trusted_transport():
            result = await self.worker.run_once()
        self.assertEqual(result, [{'outputId': str(self.identity), 'status': 'archived'}])
        self.assertEqual(self.sni, ['localhost'])
        self.assertEqual(len(self.requests), 1)
        self.assertIn(f'Host: localhost:{self.port}'.encode(), self.requests[0])
        self.assertNotIn(b'Authorization:', self.requests[0])
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, self.identity)
            file = await GeneratedOutputDao.file(db, output.file_id)
            key = file.storage_key
            self.assertEqual((file.width, file.height, file.byte_size), (24, 12, len(self.data)))
            self.assertEqual(file.sha256, hashlib.sha256(self.data).hexdigest())
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 2)
            self.assertEqual(await db.scalar(text('SELECT billing_state FROM hf_creation_job')), '0')

        def read():
            with self.storage.open_key(key) as handle:
                return handle.read()

        self.assertEqual(await asyncio.to_thread(read), self.data)
        self.assertEqual(await self.worker.run_once(), [])

    async def test_trusted_certificate_with_wrong_hostname_cannot_archive(self):
        await self.source('127.0.0.1')
        with self.trusted_transport():
            result = await self.worker.run_once()
        self.assertEqual(result[0]['status'], 'failed')
        self.assertEqual(self.requests, [])
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, self.identity)
            self.assertEqual(output.archive_state, '3')
            self.assertIsNone(output.file_id)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)

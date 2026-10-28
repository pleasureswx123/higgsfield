"""响应证据真实文件往返、损坏拒绝及写入失败保护。"""

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from exceptions.exception import ServiceWarning
from module_higgsfield.service.credential_crypto_service import CredentialKeyring
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class ResponseFileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 1000, 10000))
        crypto = ProviderResponseCryptoService(CredentialKeyring('v1', {'v1': b'a' * 32}, b'b' * 32))
        self.service = ProviderResponseStorageService(self.storage, crypto, max_bytes=1000)

    async def test_encrypted_file_roundtrip_and_wrong_identity(self) -> None:
        body = {'choices': [{'message': {'content': 'private-image-response'}}], 'usage': {'input_tokens': 12}}
        facts = await self.service.save(body, 1, 2)
        encrypted = await asyncio.to_thread((Path(self.temp.name) / facts['storage_key']).read_bytes)
        self.assertNotIn(b'private-image-response', encrypted)
        self.assertEqual(await self.service.load(facts, 1, 2), body)
        with self.assertRaises(ValueError):
            await self.service.load(facts, 1, 3)
        with self.assertRaises(ValueError):
            await self.service.load(facts | {'storage_key': 'media/' + 'a' * 32}, 1, 2)

    async def test_modified_and_oversized_files_rejected(self) -> None:
        facts = await self.service.save({'image': 'response'}, 1, 2)
        path = Path(self.temp.name) / facts['storage_key']
        await asyncio.to_thread(path.write_bytes, b'x' * (facts['byte_size'] + 10))
        with self.assertRaises(ValueError):
            await self.service.load(facts, 1, 2)
        with self.assertRaises(ValueError):
            await self.service.load(facts | {'byte_size': 1000000}, 1, 2)
        with self.assertRaises(ValueError):
            await self.service.save({'image': 'x' * 1001}, 1, 2)

    async def test_disk_error_cleans_new_file_but_collision_preserves_existing(self) -> None:
        with patch('os.fsync', side_effect=OSError('模拟磁盘故障')), self.assertRaises(ServiceWarning):
            await self.service.save({'image': 'response'}, 1, 2)
        files = await asyncio.to_thread(lambda: [p for p in Path(self.temp.name).rglob('*') if p.is_file()])
        self.assertEqual(files, [])
        identity = SimpleNamespace(hex='b' * 32)
        with patch('module_higgsfield.service.provider_response_storage_service.uuid4', return_value=identity):
            facts = await self.service.save({'original': True}, 1, 2)
            with self.assertRaises(ServiceWarning):
                await self.service.save({'overwrite': True}, 1, 2)
        self.assertEqual(await self.service.load(facts, 1, 2), {'original': True})

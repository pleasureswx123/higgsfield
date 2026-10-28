"""生成图片真实解码、声明核对、失败清理及取消中的线程IO回收。"""

import asyncio
import hashlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.image_provider_fact_vo import ProviderImage
from module_higgsfield.service.image_storage_service import ImageStorageService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class ImageStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = StorageService(StoragePolicy(self.temp.name, 'local-test', '', 100000, 10000))
        self.service = ImageStorageService(self.storage)
        buffer = io.BytesIO()
        Image.new('RGB', (16, 32), 'red').save(buffer, format='PNG')
        self.data = buffer.getvalue()
        self.picture = ProviderImage(ordinal=3, data=self.data)

    async def test_real_png_preserves_bytes_and_metadata(self) -> None:
        facts = await self.service.persist(self.picture, declared_format='png', declared_size='16x32')
        self.assertEqual(facts['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertEqual((facts['width'], facts['height'], facts['mime_type']), (16, 32, 'image/png'))
        actual = await asyncio.to_thread((Path(self.temp.name) / facts['storage_key']).read_bytes)
        self.assertEqual(actual, self.data)

    async def test_declared_mismatch_and_write_failure_leave_no_media(self) -> None:
        for fields in ({'declared_format': 'jpeg'}, {'declared_size': '32x16'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                await self.service.persist(self.picture, **fields)
        with patch('os.fsync', side_effect=OSError('模拟磁盘失败')), self.assertRaises(ServiceWarning):
            await self.service.persist(self.picture)
        files = await asyncio.to_thread(lambda: [p for p in Path(self.temp.name).rglob('*') if p.is_file()])
        self.assertEqual(files, [])

    async def test_cancel_waits_for_io_then_removes_unbound_file(self) -> None:
        started, release = threading.Event(), threading.Event()
        original = self.service._write

        def slow_write(*args) -> dict:
            started.set()
            release.wait(timeout=5)
            return original(*args)

        with patch.object(self.service, '_write', side_effect=slow_write):
            task = asyncio.create_task(self.service.persist(self.picture))
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        files = await asyncio.to_thread(lambda: [p for p in Path(self.temp.name).rglob('*') if p.is_file()])
        self.assertEqual(files, [])

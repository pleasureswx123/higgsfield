"""图片准备并发、完整性及取消回收回归。"""
import asyncio
import base64
import hashlib
import io
import tempfile
import threading
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from PIL import Image
from module_higgsfield.service.image_reference_service import ImageReferenceService
from module_higgsfield.service.image_response_service import ImageResponseService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService

class ImagePreparationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.storage = StorageService(StoragePolicy(temp.name, 'local-test', '', 100000, 10000))
        self.service = ImageReferenceService(self.storage)
        self.media, self.files, self.data = [], [], []
        for index, color in enumerate(('red', 'blue', 'green', 'white')):
            buffer = io.BytesIO()
            Image.new('RGB', (32, 32), color).save(buffer, format='PNG')
            data = buffer.getvalue()
            key = 'media/' + format(index, '032x')
            with self.storage.open_key(key, write=True) as handle:
                handle.write(data)
            sha = hashlib.sha256(data).hexdigest()
            self.data.append(data)
            self.media.append(dict(ordinal=index, mediaType='image', mediaRole='reference_image',
                byteSize=len(data), fileId=str(index), sha256=sha, mimeType='image/png'))
            self.files.append(SimpleNamespace(file_id=index, state='1', sha256=sha, storage_key=key))
        self.compiled = {'media': self.media}
        self.open_sessions = 0
        @asynccontextmanager
        async def sessions():
            self.open_sessions += 1
            try:
                yield object()
            finally:
                self.open_sessions -= 1
        self.context = SimpleNamespace(sessions=sessions, lease=object())
        for target, result in [('JobLeaseService.guard', (SimpleNamespace(input_snapshot={'compiled': self.compiled}), None)), ('AssetDao.files', self.files)]:
            patcher = patch('module_higgsfield.service.image_reference_service.' + target, AsyncMock(return_value=result))
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target == 'AssetDao.files':
                self.lookup = mock

    async def test_parallel_bound_and_original_bytes(self):
        original = self.service._encode
        barrier = threading.Barrier(2)
        active = peak = 0
        lock = threading.Lock()
        def encode(item, key):
            nonlocal active, peak
            self.assertEqual(self.open_sessions, 0)
            with lock:
                active += 1
                peak = max(peak, active)
            try:
                barrier.wait(timeout=3)
                return original(item, key)
            finally:
                with lock:
                    active -= 1
        with patch.object(self.service, '_encode', side_effect=encode):
            result = await self.service(self.context, self.compiled)
        self.assertEqual(peak, 2)
        self.lookup.assert_awaited_once()
        self.assertEqual(list(result), [0, 1, 2, 3])
        for index, value in result.items():
            self.assertEqual(base64.b64decode(value.get_secret_value().split(',')[1]), self.data[index])

    async def test_integrity_and_missing_file(self):
        self.media[0]['sha256'] = self.files[0].sha256 = '0' * 64
        with self.assertRaises(ValueError):
            await self.service(self.context, self.compiled)
        self.lookup.return_value = self.files[1:]
        with patch.object(self.service, '_encode') as encode, self.assertRaises(ValueError):
            await self.service(self.context, self.compiled)
        encode.assert_not_called()

    async def test_cancel_waits_for_started_threads(self):
        started, release = threading.Event(), threading.Event()
        active = 0
        lock = threading.Lock()
        def encode(item, key):
            nonlocal active
            with lock:
                active += 1
            started.set()
            try:
                release.wait(3)
                return 'unused'
            finally:
                with lock:
                    active -= 1
        with patch.object(self.service, '_encode', side_effect=encode):
            task = asyncio.create_task(self.service(self.context, self.compiled))
            await asyncio.to_thread(started.wait, 3)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(active, 0)

    async def test_parse_uses_background_thread(self):
        main = threading.get_ident()
        def parse(*args, **kwargs):
            self.assertNotEqual(threading.get_ident(), main)
            return 'fact'
        with patch.object(ImageResponseService, 'parse', side_effect=parse):
            self.assertEqual(await ImageResponseService.parse_async(200, {}, max_bytes=100, expected_count=1), 'fact')

    async def test_snapshot_mismatch_prevents_reads(self):
        from copy import deepcopy
        changed = deepcopy(self.compiled)
        changed['media'][0]['fileId'] = '999'
        with patch.object(self.service, '_encode') as encode, self.assertRaises(ValueError):
            await self.service(self.context, changed)
        self.lookup.assert_not_awaited()
        encode.assert_not_called()

    async def test_false_mime_is_rejected(self):
        self.media[0]['mimeType'] = 'image/jpeg'
        with self.assertRaises(ValueError):
            await self.service(self.context, self.compiled)

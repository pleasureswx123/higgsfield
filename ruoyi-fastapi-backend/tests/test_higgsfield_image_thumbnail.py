"""真实图片与临时存储验证缩略图尺寸、透明度、方向、元数据及源文件不变。"""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from exceptions.exception import ServiceWarning
from module_higgsfield.service.image_thumbnail_service import ImageThumbnailService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class ImageThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = StorageService(StoragePolicy(self.directory.name, 'local-test', '', 8 * 1024 * 1024, 4_000_000))
        self.service = ImageThumbnailService(self.storage)
        self.key = 'media/' + 'a' * 32

    def source(self, mode='RGBA', size=(1600, 800), format='PNG', **options):
        image = Image.new(mode, size, (20, 80, 140, 100) if mode == 'RGBA' else (20, 80, 140))
        self.addCleanup(image.close)
        buffer = io.BytesIO()
        image.save(buffer, format=format, **options)
        content = buffer.getvalue()
        with self.storage.open_key(self.key, write=True) as handle:
            handle.write(content)
        return content

    def generate(self, content, mime='image/png'):
        return self.service.create(self.key, hashlib.sha256(content).hexdigest(), len(content), mime)

    def test_resize_transparency_and_source_unchanged(self):
        original = self.source()
        facts = self.generate(original)
        self.assertEqual((facts['width'], facts['height']), (512, 256))
        self.assertNotEqual(facts['storage_key'], self.key)
        with self.storage.open_key(facts['storage_key']) as handle:
            encoded = handle.read()
            self.assertEqual(hashlib.sha256(encoded).hexdigest(), facts['sha256'])
            self.assertEqual(len(encoded), facts['byte_size'])
            with Image.open(io.BytesIO(encoded)) as image:
                self.assertEqual(image.format, 'WEBP')
                self.assertEqual(image.getpixel((0, 0))[3], 100)
        with self.storage.open_key(self.key) as handle:
            self.assertEqual(handle.read(), original)

    def test_exif_direction_applied_and_metadata_removed_without_upscale(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'private-author'
        original = self.source('RGB', (80, 40), 'JPEG', exif=exif)
        facts = self.generate(original, 'image/jpeg')
        self.assertEqual((facts['width'], facts['height']), (40, 80))
        with self.storage.open_key(facts['storage_key']) as handle:
            with Image.open(handle) as image:
                self.assertFalse(image.getexif())
                self.assertNotIn('icc_profile', image.info)

    def test_mismatch_and_pixel_limit_do_not_create_derived_files(self):
        original = self.source(size=(100, 100))
        for digest, size, mime in [('0' * 64, len(original), 'image/png'),
                                   (hashlib.sha256(original).hexdigest(), len(original) - 1, 'image/png'),
                                   (hashlib.sha256(original).hexdigest(), len(original), 'image/jpeg')]:
            with self.assertRaises(ServiceWarning):
                self.service.create(self.key, digest, size, mime)
        bounded = ImageThumbnailService(StorageService(StoragePolicy(self.directory.name, 'local-test', '', 8 * 1024 * 1024, 99)))
        with self.assertRaises(ServiceWarning):
            bounded.create(self.key, hashlib.sha256(original).hexdigest(), len(original), 'image/png')
        self.assertEqual(len(list((Path(self.directory.name) / 'media').iterdir())), 1)

    def test_failed_sync_removes_only_unbound_derivative(self):
        original = self.source()
        with patch('module_higgsfield.service.image_thumbnail_service.os.fsync', side_effect=OSError('写入失败')):
            with self.assertRaises(ServiceWarning):
                self.generate(original)
        self.assertEqual(len(list((Path(self.directory.name) / 'media').iterdir())), 1)
        with self.storage.open_key(self.key) as handle:
            self.assertEqual(handle.read(), original)

    def test_corrupt_and_animated_images_are_rejected(self):
        for animated in (False, True):
            with self.subTest(animated=animated):
                key = 'media/' + ('b' if animated else 'c') * 32
                content = b'not-a-valid-image'
                if animated:
                    with Image.new('RGB', (20, 20), 'red') as first, Image.new('RGB', (20, 20), 'blue') as second:
                        buffer = io.BytesIO()
                        first.save(buffer, 'WEBP', save_all=True, append_images=[second], duration=100)
                        content = buffer.getvalue()
                with self.storage.open_key(key, write=True) as handle:
                    handle.write(content)
                before = set((Path(self.directory.name) / 'media').iterdir())
                with self.assertRaises(ServiceWarning):
                    self.service.create(key, hashlib.sha256(content).hexdigest(), len(content), 'image/webp')
                self.assertEqual(set((Path(self.directory.name) / 'media').iterdir()), before)

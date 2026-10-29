"""项目图片上传按实际解码格式保存，保留类别及内容校验。"""
import hashlib
import io
import tempfile
import unittest
from PIL import Image
from exceptions.exception import ServiceWarning
from module_higgsfield.service.storage_service import StoragePolicy
from module_higgsfield.service.project_upload_storage_service import ProjectUploadStorageService

class UploadMimeTests(unittest.TestCase):
    def test_supported_images_use_actual_format(self):
        for fmt, mime in [('PNG', 'image/png'), ('JPEG', 'image/jpeg'), ('WEBP', 'image/webp')]:
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as root:
                store = ProjectUploadStorageService(StoragePolicy(root, 'local-test', '', 100000, 10000))
                buf = io.BytesIO()
                Image.new('RGB', (16, 16), 'red').save(buf, format=fmt)
                data = buf.getvalue()
                sha = hashlib.sha256(data).hexdigest()
                with store.open_key('upload-staging/0123456789abcdef0123456789abcdef', write=True) as out:
                    out.write(data)
                parts = [{'storage_key': 'upload-staging/0123456789abcdef0123456789abcdef', 'sha256': sha, 'byte_size': len(data)}]
                result = store.assemble(parts, len(data), sha, 'image/jpeg')
                self.assertEqual(result['mime_type'], mime)
                with store.open_key(result['storage_key']) as saved:
                    self.assertEqual(saved.read(), data)
                with self.assertRaises(ServiceWarning):
                    store.assemble(parts, len(data), sha, 'video/mp4')

    def test_corrupt_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            store = ProjectUploadStorageService(StoragePolicy(root, 'local-test', '', 100000, 10000))
            with self.assertRaises(ServiceWarning):
                store.verify_file(io.BytesIO(b'not an image'), 'image/jpeg')

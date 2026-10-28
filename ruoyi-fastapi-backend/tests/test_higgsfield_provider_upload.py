"""上传文件流与到期事实解析，不请求真实供应商。"""

import hashlib
import io
import unittest
from datetime import UTC, datetime, timedelta

from module_higgsfield.service.provider_upload_response_service import ProviderUploadResponseService
from module_higgsfield.service.provider_upload_stream import ProviderUploadStream


class UploadResponseTests(unittest.TestCase):
    def test_expiry_uses_earliest_fact_and_margin(self) -> None:
        now = datetime(2026, 10, 27, tzinfo=UTC)
        body = {
            'success': True,
            'file_name': 'test.png',
            'asset_type': 'image',
            'content_type': 'image/png',
            'size': 10,
            'url': 'https://example.com/file?secret=token',
            'expires_in': 3600,
            'expires_at': (now + timedelta(minutes=30)).isoformat(),
        }
        result = ProviderUploadResponseService.parse(
            200, body, received_at=now, expected_size=10, expected_mime='image/png'
        )
        self.assertEqual(result.expires_at, now + timedelta(minutes=29))
        self.assertIn('UPLOAD_EXPIRY_CONFLICT', result.issues)
        self.assertNotIn('secret=token', repr(result))
        for changes in (
            {'success': 1},
            {'size': 11},
            {'asset_type': 'video'},
            {'expires_in': None, 'expires_at': None},
            {'expires_in': 30, 'expires_at': None},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ProviderUploadResponseService.parse(
                    200, body | changes, received_at=now, expected_size=10, expected_mime='image/png'
                )


class UploadStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_reads_and_identity_changes(self) -> None:
        data = b'x' * 150000
        upload = ProviderUploadStream(
            io.BytesIO(data),
            file_name='reference.mp4',
            mime_type='video/mp4',
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            max_bytes=200000,
        )
        chunks = [part async for part in upload.chunks()]
        self.assertEqual(sum(map(len, chunks)), upload.content_length)
        self.assertLessEqual(max(map(len, chunks)), 65536)
        self.assertEqual(b''.join(chunks[1:-1]), data)
        upload.source = io.BytesIO(b'y' * len(data))
        with self.assertRaises(ValueError):
            _ = [part async for part in upload.chunks()]
